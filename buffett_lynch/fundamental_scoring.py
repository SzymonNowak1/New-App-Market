"""Buffett/Lynch 2.0 fundamental scoring implementation."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, List

from .models import FundamentalSnapshot, ScoredCompany


MEDIAN_PERCENTILE = 0.5


@dataclass
class ScoringRules:
    quality: Callable[[FundamentalSnapshot], float]
    value: Callable[[FundamentalSnapshot], float]
    growth: Callable[[FundamentalSnapshot], float]
    moat: Callable[[FundamentalSnapshot], float]
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
            moat = self.rules.moat(snap)
            risk = self.rules.risk(snap)
            total = 0.35 * quality + 0.20 * growth + 0.20 * moat + 0.15 * value + 0.10 * risk
            scored.append(
                ScoredCompany(
                    symbol=symbol,
                    quality=quality,
                    value=value,
                    growth=growth,
                    moat=moat,
                    risk=risk,
                    total=total,
                    sector=snap.sector,
                    market_cap=snap.market_cap,
                    period=snap.period,
                )
            )
        return scored


__all__ = ["FundamentalScorer", "ScoringRules"]


def _metric_with_median(metrics: Dict[str, float], *keys: str, default: float = MEDIAN_PERCENTILE) -> float:
    """Return the first available metric value or a median fallback.

    Percentile-based inputs should not default to 0.0 because missing data would
    distort scoring. The median percentile (0.5) is used when a component is
    absent or explicitly set to ``None``.
    """

    for key in keys:
        value = metrics.get(key)
        if value is not None:
            return value
    return default


def growth_score(snapshot: FundamentalSnapshot) -> float:
    """Compute GrowthScore with a penalty for volatile revenue growth.

    Stable revenue growth is rewarded more than erratic surges. The penalty is
    expected to be a pre-computed percentile that scales with revenue
    variability; higher variability reduces the resulting GrowthScore.
    """

    growth_pct = snapshot.metrics.get("growth", 0.0)
    volatility_penalty = snapshot.metrics.get("revenue_volatility_penalty", 0.0)

    return max(0.0, growth_pct - volatility_penalty)


def quality_score(snapshot: FundamentalSnapshot) -> float:
    """Compute QualityScore with a 5Y ROIC trend uplift.

    The ROIC trend percentile rewards companies whose operational efficiency is
    improving over the last five years instead of only looking at the current
    ROIC level.
    """

    roe_pct = snapshot.metrics.get("roe", 0.0)
    roic_trend_pct = snapshot.metrics.get("roic_trend_pct", 0.0)

    # Keep the ROE-driven profile while explicitly rewarding a rising ROIC trend.
    return 0.9 * roe_pct + 0.1 * roic_trend_pct


def moat_score(snapshot: FundamentalSnapshot) -> float:
    """Compute MoatScore from pricing power, reinvestment, and ROIC trend percentiles."""

    gross_margin_pct = _metric_with_median(
        snapshot.metrics, "gross_margin_percentile", "gross_margin_pct"
    )
    rd_sales_pct = _metric_with_median(
        snapshot.metrics, "r_and_d_to_sales_percentile", "rd_sales_pct"
    )
    roic_trend_pct = _metric_with_median(
        snapshot.metrics, "roic_trend_percentile", "roic_trend_pct"
    )

    return 0.4 * gross_margin_pct + 0.3 * rd_sales_pct + 0.3 * roic_trend_pct


__all__.extend(["growth_score", "moat_score", "quality_score"])

