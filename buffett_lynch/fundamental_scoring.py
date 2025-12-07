"""Buffett/Lynch 2.0 fundamental scoring implementation."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, List

from .models import FundamentalSnapshot, ScoredCompany


@dataclass
class ScoringRules:
    quality: Callable[[FundamentalSnapshot], float]
    value: Callable[[FundamentalSnapshot], float]
    growth: Callable[[FundamentalSnapshot], float]
    risk: Callable[[FundamentalSnapshot], float]


class FundamentalScorer:
    def __init__(self, rules: ScoringRules):
        self.rules = rules

    def score(self, symbol: str, fundamentals: List[FundamentalSnapshot]) -> List[ScoredCompany]:
        scored: List[ScoredCompany] = []
        for snap in fundamentals:
            quality = self.rules.quality(snap)
            value = self.rules.value(snap)
            growth = self.rules.growth(snap)
            risk = self.rules.risk(snap)
            total = 0.40 * quality + 0.25 * value + 0.20 * growth + 0.15 * risk
            scored.append(
                ScoredCompany(
                    symbol=symbol,
                    quality=quality,
                    value=value,
                    growth=growth,
                    risk=risk,
                    total=total,
                    sector=snap.sector,
                    market_cap=snap.market_cap,
                )
            )
        return scored


__all__ = ["FundamentalScorer", "ScoringRules"]

