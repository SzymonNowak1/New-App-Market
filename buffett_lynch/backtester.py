"""Backtesting engine for the Buffett/Lynch 2.0 strategy."""
from __future__ import annotations

import math
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

    def run(
        self,
        spy_prices: List[PriceBar],
        price_history: Dict[str, List[PriceBar]],
        fundamentals: Dict[str, List[ScoredCompany]],
        top100_by_year: Dict[str, List[str]],
        fx_history: Dict[str, List[PriceBar]],
    ) -> BacktestReport:
        regime_map = self.execution.bull_bear(spy_prices)
        sma_cache: Dict[str, Dict[str, float]] = {
            symbol: sma(prices, self.portfolio_manager.rebalance_cfg.sma_lookback)
            for symbol, prices in price_history.items()
        }
        equity_curve: List[Tuple[str, float]] = []
        holdings: Dict[str, Position] = {}
        currency_map: Dict[str, str] = {}
        daily_returns: List[float] = []
        bull_days = bear_days = 0
        transactions = 0

        spy_dates = [bar.date for bar in spy_prices]
        capital_pln = 100000.0
        prev_value = capital_pln

        for date in spy_dates:
            regime = regime_map.get(date)
            if regime == "bull":
                bull_days += 1
            elif regime == "bear":
                bear_days += 1

            year = date[:4]
            top100 = top100_by_year.get(year, [])
            scored_today: List[ScoredCompany] = []
            for symbol, scored_list in fundamentals.items():
                for score in scored_list:
                    if score.market_cap and score.total is not None:
                        if score.symbol == symbol and score.market_cap and score.total and score.sector:
                            if score.total >= 0 and score.total is not None and score.market_cap is not None:
                                if score.symbol not in [s.symbol for s in scored_today]:
                                    scored_today.append(score)
            picks = self.portfolio_manager.pick_top(scored_today)
            orders = self.execution.generate_orders(
                date,
                picks,
                top100,
                spy_regime=regime or "bear",
                price_map={s: (price_history.get(s, [{}])[-1].close if price_history.get(s) else 0) for s in top100},
                sma_map=sma_cache,
                portfolio=holdings,
            )
            transactions += len(orders)

            # Simplified fill: adjust positions by target weight using available capital
            for order in orders:
                price = order.price or price_history.get(order.symbol, [{}])[-1].close if price_history.get(order.symbol) else 0
                if price == 0:
                    continue
                if order.action == "SELL":
                    if order.symbol in holdings:
                        capital_pln += holdings[order.symbol].quantity * price
                        del holdings[order.symbol]
                else:
                    quantity = (capital_pln * self.portfolio_manager.rebalance_cfg.max_position) / price
                    holdings[order.symbol] = Position(order.symbol, quantity, order.currency, self.portfolio_manager.rebalance_cfg.max_position, price)
                    capital_pln -= quantity * price
                    currency_map[order.symbol] = order.currency

            portfolio_value = capital_pln
            for symbol, pos in holdings.items():
                latest_price = price_history.get(symbol, [])
                if latest_price:
                    portfolio_value += pos.quantity * latest_price[-1].close
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


__all__ = ["Backtester", "BacktestReport"]

