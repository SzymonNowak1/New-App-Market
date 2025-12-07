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

    def generate_orders(
        self,
        date: str,
        picks: List[ScoredCompany],
        top100: List[str],
        spy_regime: str,
        price_map: Dict[str, float],
        sma_map: Dict[str, Dict[str, float]],
        portfolio: Dict[str, Position],
    ) -> List[Order]:
        orders: List[Order] = []
        if spy_regime == "bear":
            for pos in portfolio.values():
                orders.append(Order(pos.symbol, "SELL", pos.quantity, pos.currency, reason="Bear regime"))
            return orders

        total_scores = sorted((p.total for p in picks), reverse=True)
        median_total = total_scores[len(total_scores) // 2] if total_scores else 0

        allowed = [p for p in picks if p.symbol in top100 and p.value >= self.cfg.min_value_score]
        targets = {p.symbol: p for p in allowed if p.total >= median_total}

        for pos in list(portfolio.values()):
            sma_value = sma_map.get(pos.symbol, {}).get(date)
            if sma_value is None:
                continue
            if price_map.get(pos.symbol, 0) < sma_value:
                orders.append(Order(pos.symbol, "SELL", pos.quantity, pos.currency, reason="Price below SMA200"))
            elif pos.symbol not in top100:
                orders.append(Order(pos.symbol, "SELL", pos.quantity, pos.currency, reason="Lost TOP100"))
            elif pos.symbol not in targets:
                orders.append(Order(pos.symbol, "SELL", pos.quantity, pos.currency, reason="Below median score"))
            elif targets[pos.symbol].value < self.cfg.min_value_score:
                orders.append(Order(pos.symbol, "SELL", pos.quantity, pos.currency, reason="Low ValueScore"))

        for pick in allowed:
            sma_value = sma_map.get(pick.symbol, {}).get(date)
            price = price_map.get(pick.symbol)
            if price is None or sma_value is None:
                continue
            if price <= sma_value:
                continue
            if pick.symbol not in portfolio:
                orders.append(Order(pick.symbol, "BUY", 0.0, "USD", reason="Enter top portfolio", price=price))

        return orders


__all__ = ["ExecutionEngine", "sma"]

