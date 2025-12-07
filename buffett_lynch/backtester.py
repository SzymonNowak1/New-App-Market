"""Backtesting engine for the Buffett/Lynch 2.0 strategy."""
from __future__ import annotations

import math
from datetime import datetime
from dataclasses import dataclass
from typing import Dict, List, Tuple

from .config import BacktestConfig, PortfolioConfig, RebalancingConfig
from .currency_engine import CurrencyEngine
from .execution_engine import ExecutionEngine, sma
from .fundamental_scoring import FundamentalScorer
from .models import Position, PriceBar, ScoredCompany
from .portfolio_manager import PortfolioManager
from .universe_builder import UniverseBuilder


@dataclass
class BacktestReport:
    cagr: float
    max_drawdown: float
    sharpe: float
    transactions: int
    avg_holding_days: float
    bull_exposure: float
    bear_exposure: float
    equity_curve: List[Tuple[str, float]]


class Backtester:
    def __init__(
        self,
        universe: UniverseBuilder,
        scorer: FundamentalScorer,
        portfolio_manager: PortfolioManager,
        execution: ExecutionEngine,
        currency: CurrencyEngine,
        config: BacktestConfig,
    ):
        self.universe = universe
        self.scorer = scorer
        self.portfolio_manager = portfolio_manager
        self.execution = execution
        self.currency = currency
        self.config = config
        # Guarantee an SMA lookback attribute on the rebalancing configuration so downstream
        # consumers never fail when older objects lack the field (e.g., during CI runs).
        if not hasattr(self.portfolio_manager.rebalance_cfg, "sma_lookback"):
            self.portfolio_manager.rebalance_cfg.sma_lookback = self.execution.cfg.sma_lookback

    def run(
        self,
        spy_prices: List[PriceBar],
        price_history: Dict[str, List[PriceBar]],
        fundamentals: Dict[str, List[ScoredCompany]],
        top100_by_year: Dict[str, List[str]],
        fx_history: Dict[str, List[PriceBar]],
    ) -> BacktestReport:
        regime_map = self.execution.bull_bear(spy_prices)
        lookback = getattr(
            self.portfolio_manager.rebalance_cfg,
            "sma_lookback",
            self.execution.cfg.sma_lookback,
        )
        sma_cache: Dict[str, Dict[str, float]] = {
            symbol: sma(prices, lookback) for symbol, prices in price_history.items()
        }
        price_lookup: Dict[str, Dict[str, float]] = {
            symbol: {bar.date: bar.close for bar in prices} for symbol, prices in price_history.items()
        }
        rebalance_dates = self._quarter_starts([bar.date for bar in spy_prices])
        equity_curve: List[Tuple[str, float]] = []
        holdings: Dict[str, Position] = {}
        currency_map: Dict[str, str] = {}
        daily_returns: List[float] = []
        bull_days = bear_days = 0
        transactions = 0
        current_scores: List[ScoredCompany] = []

        spy_dates = [bar.date for bar in spy_prices]
        capital_pln = self.config.initial_capital
        prev_value = capital_pln

        for date in spy_dates:
            regime = regime_map.get(date)
            capital_pln += self.config.contributions.get(date, 0.0)
            if regime == "bull":
                bull_days += 1
            elif regime == "bear":
                bear_days += 1

            year = date[:4]
            top100 = top100_by_year.get(year, [])
            if date in rebalance_dates or not current_scores:
                current_scores = self._scores_for_year(fundamentals, year)
            picks = sorted(current_scores, key=lambda s: s.total, reverse=True)
            rebalance_due = date in rebalance_dates
            orders = self.execution.generate_orders(
                date,
                picks,
                top100,
                spy_regime=regime or "bear",
                price_map={s: self._get_price(price_lookup, price_history, s, date) for s in top100},
                sma_map=sma_cache,
                portfolio=holdings,
                rebalance_due=rebalance_due,
            )
            transactions += len(orders)

            # Simplified fill: adjust positions by target weight using available capital
            for order in orders:
                price = order.price or self._get_price(price_lookup, price_history, order.symbol, date)
                if price == 0:
                    continue
                if order.action == "SELL":
                    if not self._allow_sell(order, holdings, date):
                        continue
                    if order.symbol in holdings:
                        capital_pln += holdings[order.symbol].quantity * price
                        del holdings[order.symbol]
                else:
                    quantity = (capital_pln * self.portfolio_manager.rebalance_cfg.max_position) / price
                    holdings[order.symbol] = Position(
                        order.symbol,
                        quantity,
                        order.currency,
                        self.portfolio_manager.rebalance_cfg.max_position,
                        price,
                        date,
                    )
                    capital_pln -= quantity * price
                    currency_map[order.symbol] = order.currency

            portfolio_value = capital_pln
            for symbol, pos in holdings.items():
                day_price = self._get_price(price_lookup, price_history, symbol, date)
                if day_price:
                    portfolio_value += pos.quantity * day_price
            portfolio_pln = self.currency.portfolio_to_pln({s: portfolio_value for s in ["portfolio"]}, fx_history, date, {"portfolio": "PLN"})
            equity_curve.append((date, portfolio_pln))
            if prev_value > 0:
                daily_returns.append((portfolio_pln - prev_value) / prev_value)
            prev_value = portfolio_pln

        cagr = self._cagr(equity_curve)
        max_dd = self._max_drawdown(equity_curve)
        sharpe = self._sharpe(daily_returns)
        avg_hold = self._avg_holding_days(holdings)
        total_days = bull_days + bear_days or 1
        report = BacktestReport(
            cagr=cagr,
            max_drawdown=max_dd,
            sharpe=sharpe,
            transactions=transactions,
            avg_holding_days=avg_hold,
            bull_exposure=bull_days / total_days,
            bear_exposure=bear_days / total_days,
            equity_curve=equity_curve,
        )
        return report

    def _cagr(self, equity_curve: List[Tuple[str, float]]) -> float:
        if not equity_curve:
            return 0.0
        start_value = equity_curve[0][1]
        end_value = equity_curve[-1][1]
        years = max(1, len(equity_curve) / 252)
        return (end_value / start_value) ** (1 / years) - 1

    def _max_drawdown(self, equity_curve: List[Tuple[str, float]]) -> float:
        peak = -math.inf
        max_dd = 0.0
        for _, value in equity_curve:
            peak = max(peak, value)
            if peak > 0:
                dd = (peak - value) / peak
                max_dd = max(max_dd, dd)
        return max_dd

    def _sharpe(self, daily_returns: List[float], risk_free: float = 0.0) -> float:
        if not daily_returns:
            return 0.0
        mean = sum(daily_returns) / len(daily_returns)
        variance = sum((r - mean) ** 2 for r in daily_returns) / len(daily_returns)
        std = math.sqrt(variance)
        if std == 0:
            return 0.0
        return (mean - risk_free / 252) / std * math.sqrt(252)

    def _avg_holding_days(self, holdings: Dict[str, Position]) -> float:
        # Placeholder: without transaction history we assume weekly rebalancing
        return 5.0

    def _scores_for_year(self, fundamentals: Dict[str, List[ScoredCompany]], year: str) -> List[ScoredCompany]:
        """Return the most recent scores up to the requested year for each symbol."""
        year_int = int(year)
        scores: List[ScoredCompany] = []
        for symbol, entries in fundamentals.items():
            eligible = [s for s in entries if s.market_cap > 0 and int(s.period) <= year_int]
            if not eligible:
                continue
            latest = sorted(eligible, key=lambda s: int(s.period), reverse=True)[0]
            scores.append(latest)
        return scores

    def _quarter_starts(self, dates: List[str]) -> List[str]:
        seen = set()
        starts: List[str] = []
        for date in sorted(dates):
            dt = datetime.fromisoformat(date)
            quarter = (dt.month - 1) // 3
            key = (dt.year, quarter)
            if key not in seen:
                seen.add(key)
                starts.append(date)
        return starts

    def _allow_sell(self, order: Order, holdings: Dict[str, Position], date: str) -> bool:
        """Enforce a 90-day minimum holding period for non-fundamental exits."""
        fundamental_reasons = {"Bear regime", "Lost TOP100", "ValueScore guardrail", "Below TOP3N buffer"}
        if order.reason in fundamental_reasons:
            return True
        pos = holdings.get(order.symbol)
        if not pos or not pos.entry_date:
            return True
        held_days = (datetime.fromisoformat(date) - datetime.fromisoformat(pos.entry_date)).days
        return held_days >= 90

    def _get_price(
        self,
        price_lookup: Dict[str, Dict[str, float]],
        price_history: Dict[str, List[PriceBar]],
        symbol: str,
        date: str,
    ) -> float:
        """Return the daily close if available, otherwise fall back to the latest known price."""
        price = price_lookup.get(symbol, {}).get(date)
        if price is not None:
            return price
        history = price_history.get(symbol, [])
        return history[-1].close if history else 0


__all__ = ["Backtester", "BacktestReport"]

