"""Raw moat metric enrichment utilities.

This module computes the raw moat inputs (gross margin %, R&D/Sales %, and
5-year ROIC trend) for each ``FundamentalSnapshot`` before percentile
evaluation. Missing inputs are left absent so downstream percentile logic can
apply median fallbacks consistently.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Mapping

import numpy as np

from .models import FundamentalSnapshot


def _linear_trend(values: List[float]) -> float:
    if len(values) < 2:
        return 0.0
    x = np.arange(len(values))
    slope, _ = np.polyfit(x, values, 1)
    return float(slope)


@dataclass
class FundamentalRawMetrics:
    """Derive raw moat components from fundamental inputs."""

    def enrich_moat_raw_metrics(
        self, fundamentals: Mapping[str, List[FundamentalSnapshot]]
    ) -> Dict[str, List[FundamentalSnapshot]]:
        enriched: Dict[str, List[FundamentalSnapshot]] = {}
        for symbol, snaps in fundamentals.items():
            enriched_snaps: List[FundamentalSnapshot] = []
            for snap in snaps:
                metrics = dict(snap.metrics)

                gross_profit = metrics.get("gross_profit")
                revenue = metrics.get("revenue")
                if gross_profit is not None and revenue:
                    metrics["gross_margin_pct"] = float(gross_profit) / float(revenue) * 100.0

                rd_expense = metrics.get("r_and_d_expense")
                if rd_expense is not None and revenue:
                    metrics["rd_sales_pct"] = float(rd_expense) / float(revenue) * 100.0

                roic_history = [float(v) for v in metrics.get("roic_history") or [] if v is not None]
                if len(roic_history) >= 2:
                    trend_window = roic_history[-5:]
                    metrics["roic_trend_pct"] = _linear_trend(trend_window)

                enriched_snaps.append(
                    FundamentalSnapshot(
                        period=snap.period,
                        market_cap=snap.market_cap,
                        sector=snap.sector,
                        metrics=metrics,
                    )
                )
            enriched[symbol] = enriched_snaps

        return enriched


__all__ = ["FundamentalRawMetrics"]
