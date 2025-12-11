"""Fundamental metric enrichment utilities.

This module computes moat-related percentile metrics for each
``FundamentalSnapshot`` within a yearly universe and applies deterministic
median fallbacks when raw inputs are missing.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Mapping

import numpy as np

from .models import FundamentalSnapshot


MOAT_OUTPUT_KEYS = {
    "gross_margin_percentile": "gross_margin_pct",
    "r_and_d_to_sales_percentile": "rd_sales_pct",
    "roic_trend_percentile": "roic_trend_pct",
}


def _percentile_rank(value: float, peers: List[float]) -> float:
    if not peers:
        return 0.0
    arr = np.array(peers, dtype=float)
    return float((arr <= value).sum()) / len(arr) * 100.0


def _median(values: List[float]) -> float:
    clean = [v for v in values if v is not None]
    return float(np.median(clean)) if clean else 0.0


@dataclass
class FundamentalMetrics:
    """Compute and attach moat percentile metrics to fundamental snapshots."""

    def enrich_moat_percentiles(
        self, fundamentals: Mapping[str, List[FundamentalSnapshot]]
    ) -> Dict[str, List[FundamentalSnapshot]]:
        # Collect raw metric values per year for percentile evaluation
        year_values: Dict[str, Dict[str, List[float]]] = {}
        for snaps in fundamentals.values():
            for snap in snaps:
                per_metric = year_values.setdefault(snap.period, {key: [] for key in MOAT_OUTPUT_KEYS})
                for output_key, source_key in MOAT_OUTPUT_KEYS.items():
                    per_metric.setdefault(output_key, [])
                    value = snap.metrics.get(source_key)
                    if value is not None:
                        per_metric[output_key].append(value)

        # Compute medians and peers that inject medians for missing values
        medians: Dict[str, Dict[str, float]] = {}
        peers: Dict[str, Dict[str, List[float]]] = {}
        for year, metric_values in year_values.items():
            medians[year] = {}
            peers[year] = {}
            for output_key, values in metric_values.items():
                med = _median(values)
                medians[year][output_key] = med
                peers[year][output_key] = []

        # Build peer lists with medians filling missing values
        for snaps in fundamentals.values():
            for snap in snaps:
                for output_key, source_key in MOAT_OUTPUT_KEYS.items():
                    value = snap.metrics.get(source_key)
                    year = snap.period
                    fallback = medians.get(year, {}).get(output_key, 0.0)
                    peers[year][output_key].append(value if value is not None else fallback)

        enriched: Dict[str, List[FundamentalSnapshot]] = {}
        for symbol, snaps in fundamentals.items():
            enriched_snaps: List[FundamentalSnapshot] = []
            for snap in snaps:
                metrics = dict(snap.metrics)
                for output_key, source_key in MOAT_OUTPUT_KEYS.items():
                    year = snap.period
                    fallback = medians.get(year, {}).get(output_key, 0.0)
                    value = metrics.get(source_key)
                    with_fallback = value if value is not None else fallback
                    percentile = _percentile_rank(with_fallback, peers.get(year, {}).get(output_key, []))
                    metrics[output_key] = percentile
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


__all__ = ["FundamentalMetrics", "MOAT_OUTPUT_KEYS"]
