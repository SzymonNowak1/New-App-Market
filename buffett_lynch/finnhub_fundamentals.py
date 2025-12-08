"""Finnhub-backed fundamentals data source."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

import requests

from .data_loader import FundamentalsDataSource
from .models import FundamentalSnapshot


@dataclass
class FinnhubFundamentalsSource(FundamentalsDataSource):
    """Load fundamental snapshots from Finnhub endpoints with caching."""

    api_key: str
    symbols: Optional[List[str]] = None
    cache_dir: Path = field(default_factory=lambda: Path("data/finnhub_cache"))
    _cache: Dict[str, List[FundamentalSnapshot]] = field(default_factory=dict, init=False, repr=False)

    def __post_init__(self) -> None:
        if not self.api_key:
            raise ValueError("FINNHUB_API_KEY is required for FinnhubFundamentalsSource")
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def fundamentals(self, symbol: str) -> List[FundamentalSnapshot]:
        if symbol in self._cache:
            return self._cache[symbol]

        cached = self._load_cache(symbol)
        if cached is not None:
            self._cache[symbol] = cached
            return cached

        financials = self._fetch_financials(symbol)
        metrics = self._fetch_metrics(symbol)
        snapshots = self._build_snapshots(symbol, financials, metrics)
        self._cache[symbol] = snapshots
        self._write_cache(symbol, snapshots)
        return snapshots

    def all_fundamentals(self) -> Dict[str, List[FundamentalSnapshot]]:
        symbols = self.symbols or list(self._cache.keys())
        fundamentals: Dict[str, List[FundamentalSnapshot]] = {}
        for symbol in symbols:
            fundamentals[symbol] = self.fundamentals(symbol)
        return fundamentals

    # --- Finnhub helpers -------------------------------------------------
    def _fetch_financials(self, symbol: str) -> Dict:
        url = "https://finnhub.io/api/v1/stock/financials-reported"
        params = {"symbol": symbol, "freq": "annual", "token": self.api_key}
        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()
        return response.json() or {}

    def _fetch_metrics(self, symbol: str) -> Dict:
        url = "https://finnhub.io/api/v1/stock/metric"
        params = {"symbol": symbol, "metric": "all", "token": self.api_key}
        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()
        return response.json() or {}

    def _build_snapshots(self, symbol: str, financials_json: Dict, metrics_json: Dict) -> List[FundamentalSnapshot]:
        reports = financials_json.get("data") or []
        metric_block = metrics_json.get("metric", {}) or {}
        series = metrics_json.get("series", {}).get("annual", {}) if metrics_json else {}

        market_cap = float(metric_block.get("marketCapitalization") or metric_block.get("market_capitalization") or 0.0)
        sector = metric_block.get("sector") or metric_block.get("industry") or "Unknown"
        beta = metric_block.get("beta")
        pe = metric_block.get("peNormalizedAnnual") or metric_block.get("peBasicExclExtraTTM") or metric_block.get("peTTM")

        roic_series = self._parse_series(series.get("roic") or [])
        roe_series = self._parse_series(series.get("roe") or [])

        snapshots: List[FundamentalSnapshot] = []
        revenue_history: Dict[str, float] = {}

        for report in reports:
            period = report.get("year") or report.get("period") or ""
            if isinstance(period, str) and len(period) >= 4:
                year = period[:4]
            else:
                year = str(period)

            fields = self._flatten_report(report.get("report") or {})
            revenue = self._first_present(fields, "revenue", "totalRevenue")
            gross_profit = self._first_present(fields, "grossProfit")
            rd_expense = self._first_present(fields, "researchAndDevelopment", "rdExpense")

            if revenue is not None:
                revenue_history[year] = float(revenue)

            metrics: Dict[str, float] = {}
            if revenue is not None:
                metrics["revenue"] = float(revenue)
            if gross_profit is not None:
                metrics["gross_profit"] = float(gross_profit)
            if rd_expense is not None:
                metrics["r_and_d_expense"] = float(rd_expense)

            roe_value = self._series_lookup(roe_series, year)
            if roe_value is not None:
                metrics["roe"] = float(roe_value)
            elif metric_block.get("roe") is not None:
                metrics["roe"] = float(metric_block.get("roe"))

            volatility = float(beta) * 20.0 if beta is not None else None
            if volatility is not None:
                metrics["volatility"] = volatility
            if pe is not None:
                metrics["pe"] = float(pe)

            roic_value = self._series_lookup(roic_series, year)
            if roic_value is not None:
                metrics.setdefault("roic_history", [])
                metrics["roic_history"].append(float(roic_value))

            snapshots.append(
                FundamentalSnapshot(
                    period=str(year),
                    market_cap=market_cap,
                    sector=sector,
                    metrics=metrics,
                )
            )

        snapshots = sorted(snapshots, key=lambda s: s.period)
        self._attach_growth_and_volatility(snapshots, revenue_history)
        self._attach_roic_history(snapshots, roic_series, metric_block)
        return snapshots

    def _attach_growth_and_volatility(self, snaps: List[FundamentalSnapshot], revenue_history: Dict[str, float]) -> None:
        years_sorted = sorted(revenue_history.keys())
        growth_series: Dict[str, float] = {}
        for idx, year in enumerate(years_sorted):
            if idx == 0:
                continue
            prev_year = years_sorted[idx - 1]
            prev_rev = revenue_history.get(prev_year)
            curr_rev = revenue_history.get(year)
            if prev_rev and curr_rev is not None:
                growth_series[year] = (curr_rev - prev_rev) / prev_rev * 100.0

        growth_values = list(growth_series.values())
        volatility_penalty = float(self._std(growth_values)) if growth_values else 0.0

        for snap in snaps:
            year = snap.period
            metrics = dict(snap.metrics)
            if year in growth_series:
                metrics["growth"] = growth_series[year]
            if volatility_penalty:
                metrics["revenue_volatility_penalty"] = volatility_penalty
            snap.metrics = metrics

    def _attach_roic_history(self, snaps: List[FundamentalSnapshot], roic_series: Dict[str, float], metric_block: Dict) -> None:
        if not roic_series and metric_block.get("roic") is not None:
            # Use flat ROIC across periods when only a point estimate exists
            for snap in snaps:
                snap.metrics["roic_history"] = [float(metric_block["roic"])]
            return

        for snap in snaps:
            history: List[float] = []
            for year, value in sorted(roic_series.items()):
                if year <= snap.period:
                    history.append(float(value))
            if history:
                snap.metrics["roic_history"] = history

    def _parse_series(self, series: List[Dict]) -> Dict[str, float]:
        values: Dict[str, float] = {}
        for item in series:
            period = item.get("period") or item.get("date") or ""
            if isinstance(period, str) and len(period) >= 4:
                year = period[:4]
            else:
                year = str(period)
            data = item.get("v") if "v" in item else item.get("value")
            if data is not None:
                values[year] = float(data)
        return values

    def _series_lookup(self, series: Dict[str, float], year: str) -> Optional[float]:
        if year in series:
            return series[year]
        return None

    def _flatten_report(self, report: Dict) -> Dict[str, float]:
        flattened: Dict[str, float] = {}
        for section in report.values():
            if isinstance(section, dict):
                for key, value in section.items():
                    flattened[key] = value
        return flattened

    def _first_present(self, mapping: Dict[str, float], *keys: str) -> Optional[float]:
        for key in keys:
            if key in mapping and mapping[key] is not None:
                return mapping[key]
        return None

    def _std(self, values: List[float]) -> float:
        if len(values) < 2:
            return 0.0
        mean = sum(values) / len(values)
        variance = sum((v - mean) ** 2 for v in values) / (len(values) - 1)
        return variance ** 0.5

    def _cache_path(self, symbol: str) -> Path:
        return self.cache_dir / f"{symbol}_fundamentals.json"

    def _load_cache(self, symbol: str) -> Optional[List[FundamentalSnapshot]]:
        path = self._cache_path(symbol)
        if not path.exists():
            return None
        data = json.loads(path.read_text())
        snaps: List[FundamentalSnapshot] = []
        for item in data.get("snapshots", []):
            snaps.append(
                FundamentalSnapshot(
                    period=item["period"],
                    market_cap=item.get("market_cap", 0.0),
                    sector=item.get("sector", "Unknown"),
                    metrics=item.get("metrics", {}),
                )
            )
        return snaps

    def _write_cache(self, symbol: str, snaps: List[FundamentalSnapshot]) -> None:
        path = self._cache_path(symbol)
        serializable = {
            "snapshots": [
                {
                    "period": snap.period,
                    "market_cap": snap.market_cap,
                    "sector": snap.sector,
                    "metrics": snap.metrics,
                }
                for snap in snaps
            ]
        }
        path.write_text(json.dumps(serializable))


__all__ = ["FinnhubFundamentalsSource"]
