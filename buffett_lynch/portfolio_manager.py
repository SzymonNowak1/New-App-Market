"""Portfolio construction, weighting, and rebalancing."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple

from .config import PortfolioConfig, RebalancingConfig
from .models import Order, Position, ScoredCompany


@dataclass
class TargetAllocation:
    symbol: str
    weight: float
    score: ScoredCompany


class PortfolioManager:
    def __init__(self, portfolio_cfg: PortfolioConfig, rebalance_cfg: RebalancingConfig):
        self.portfolio_cfg = portfolio_cfg
        self.rebalance_cfg = rebalance_cfg

    def pick_top(self, scored: List[ScoredCompany]) -> List[ScoredCompany]:
        universe_sorted = sorted(scored, key=lambda s: s.total, reverse=True)
        return universe_sorted[: self.portfolio_cfg.top_n]

    def build_weights(self, picks: List[ScoredCompany]) -> List[TargetAllocation]:
        quality_sum = sum(p.quality for p in picks) or 1.0
        raw = [TargetAllocation(symbol=p.symbol, weight=p.quality / quality_sum, score=p) for p in picks]
        constrained = self._apply_constraints(raw)
        return constrained

    def _apply_constraints(self, allocations: List[TargetAllocation]) -> List[TargetAllocation]:
        cfg = self.rebalance_cfg
        # Sector caps
        sector_weight: Dict[str, float] = {}
        for alloc in allocations:
            sector_weight.setdefault(alloc.score.sector, 0.0)
            sector_weight[alloc.score.sector] += alloc.weight
        for alloc in allocations:
            if sector_weight[alloc.score.sector] > cfg.max_sector_weight:
                scale = cfg.max_sector_weight / sector_weight[alloc.score.sector]
                alloc.weight *= scale
        # Clamp min and max
        for alloc in allocations:
            alloc.weight = max(cfg.min_position, min(cfg.max_position, alloc.weight))
        # Renormalize
        total = sum(a.weight for a in allocations) or 1.0
        for alloc in allocations:
            alloc.weight /= total
        return allocations

    def rebalance_orders(self, current: Dict[str, Position], targets: List[TargetAllocation],
                         prices: Dict[str, float], currency: str) -> List[Order]:
        target_map = {t.symbol: t for t in targets}
        orders: List[Order] = []
        for symbol, pos in current.items():
            if symbol not in target_map:
                orders.append(Order(symbol, "SELL", pos.quantity, pos.currency, reason="Removed from target"))
        for alloc in targets:
            price = prices.get(alloc.symbol)
            if price is None or price == 0:
                continue
            target_value = alloc.weight
            current_value = current.get(alloc.symbol, Position(alloc.symbol, 0.0, currency, 0.0, 0.0))
            delta_value = target_value - current_value.weight
            if abs(delta_value) < 1e-6:
                continue
            quantity = delta_value / price
            action = "BUY" if quantity > 0 else "SELL"
            orders.append(Order(alloc.symbol, action, abs(quantity), currency, reason="Rebalance", price=price))
        return orders


__all__ = ["PortfolioManager", "TargetAllocation"]

