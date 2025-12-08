"""Signal engine applying Buffett/Lynch 2.0 trading rules."""
from __future__ import annotations

from typing import Dict, List

from .config import PortfolioConfig
from .models import Order, Position, PriceBar, ScoredCompany


def sma(prices: List[PriceBar], lookback: int) -> Dict[str, float]:
    values: Dict[str, float] = {}
    window: List[float] = []
    for bar in prices:
        window.append(bar.close)
        if len(window) > lookback:
            window.pop(0)
        if len(window) == lookback:
            values[bar.date] = sum(window) / lookback
    return values


class ExecutionEngine:
    def __init__(self, portfolio_cfg: PortfolioConfig):
        self.cfg = portfolio_cfg

    def bull_bear(self, spy_prices: List[PriceBar]) -> Dict[str, str]:
        trend = sma(spy_prices, self.cfg.sma_lookback)
        regime: Dict[str, str] = {}
        for bar in spy_prices:
            avg = trend.get(bar.date)
            if avg is None:
                continue
            regime[bar.date] = "bull" if bar.close >= avg else "bear"
        return regime

    def bear_asset(self, base_currency: str | None = None) -> tuple[str, str]:
        """Return the preferred T-Bill ETF symbol and its currency."""
        if base_currency and base_currency in self.cfg.bear_etfs:
            return self.cfg.bear_etfs[base_currency], base_currency
        if "USD" in self.cfg.bear_etfs:
            return self.cfg.bear_etfs["USD"], "USD"
        # Fall back to the first configured ETF
        currency, symbol = next(iter(self.cfg.bear_etfs.items()))
        return symbol, currency

    def generate_orders(
        self,
        date: str,
        picks: List[ScoredCompany],
        top100: List[str],
        spy_regime: str,
        price_map: Dict[str, float],
        sma_map: Dict[str, Dict[str, float]],
        portfolio: Dict[str, Position],
        bear_asset: tuple[str, str] | None = None,
        rebalance_due: bool = True,
    ) -> List[Order]:
        orders: List[Order] = []
        if not rebalance_due:
            return orders
        bear_symbol, bear_currency = bear_asset or self.bear_asset()
        if spy_regime == "bear":
            for pos in portfolio.values():
                if pos.symbol == bear_symbol:
                    continue
                orders.append(Order(pos.symbol, "SELL", pos.quantity, pos.currency, reason="Bear regime"))
            # Rotate remaining capital into the T-Bill ETF for safety
            if price_map.get(bear_symbol):
                if bear_symbol not in portfolio:
                    orders.append(
                        Order(
                            bear_symbol,
                            "BUY",
                            0.0,
                            bear_currency,
                            reason="Bear regime T-Bill",
                            price=price_map.get(bear_symbol),
                        )
                    )
            return orders

        sorted_picks = [p for p in sorted(picks, key=lambda p: p.total, reverse=True) if p.symbol in top100]
        top_n = self.cfg.top_n
        top_buy = sorted_picks[:top_n]
        top_hold = sorted_picks[: self.cfg.hold_multiplier * top_n]
        top_hold_symbols = {p.symbol for p in top_hold}
        pick_map = {p.symbol: p for p in sorted_picks}

        for pos in list(portfolio.values()):
            sma_value = sma_map.get(pos.symbol, {}).get(date)
            price = price_map.get(pos.symbol, 0)
            pick = pick_map.get(pos.symbol)

            if pos.symbol not in top100:
                orders.append(Order(pos.symbol, "SELL", pos.quantity, pos.currency, reason="Lost TOP100"))
                continue

            if pick and pick.value < self.cfg.min_value_score:
                orders.append(Order(pos.symbol, "SELL", pos.quantity, pos.currency, reason="ValueScore guardrail"))
                continue

            if pos.symbol not in top_hold_symbols:
                orders.append(Order(pos.symbol, "SELL", pos.quantity, pos.currency, reason="Below TOP3N buffer"))
                continue

            if sma_value is not None and price < sma_value:
                orders.append(Order(pos.symbol, "SELL", pos.quantity, pos.currency, reason="Price below SMA200"))

        if rebalance_due:
            for pick in top_buy:
                sma_value = sma_map.get(pick.symbol, {}).get(date)
                price = price_map.get(pick.symbol)
                if price is None or sma_value is None:
                    continue
                if price <= sma_value:
                    continue
                if pick.value < self.cfg.min_value_score:
                    continue
                if pick.symbol not in portfolio:
                    orders.append(Order(pick.symbol, "BUY", 0.0, "USD", reason="Enter TOP15", price=price))

        return orders


__all__ = ["ExecutionEngine", "sma"]

