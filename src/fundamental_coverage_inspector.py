"""Inspect fundamental data coverage using the existing Buffett/Lynch pipeline."""
from __future__ import annotations

import os
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from statistics import mean
from typing import Dict, List, Tuple
from urllib.error import URLError

from .data_loader import DataLoader
from .universe_builder import UniverseBuilder
from .main import build_data_sources

# Ensure repository root on path for module imports
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from buffett_lynch.data_loader import DataLoader, InMemorySource
from buffett_lynch.universe_builder import UniverseBuilder
from buffett_lynch.fundamental_scoring import FundamentalScorer, ScoringRules, growth_score, moat_score, quality_score
from buffett_lynch.models import FundamentalSnapshot, PriceBar
from buffett_lynch.config import StrategyConfig, BacktestConfig
from buffett_lynch.finnhub_fundamentals import FinnhubFundamentalsSource

# Fallback synthetic fundamentals helper from the CI/backtest runner
from backtester import _fundamentals, _price_series


METRICS = [
    "revenue",
    "gross_profit",
    "r_and_d_expense",
    "roic_history",
    "roe",
    "growth",
    "revenue_volatility_penalty",
    "gross_margin_pct",
    "rd_sales_pct",
    "roic_trend_pct",
    "gross_margin_percentile",
    "r_and_d_to_sales_percentile",
    "roic_trend_percentile",
]


@dataclass
class CoverageResult:
    coverage: Dict[Tuple[str, str], Dict[str, bool]]
    symbols: List[str]
    periods: List[str]


def _build_loader(start_date: str, end_date: str) -> Tuple[DataLoader, List[str], Dict[str, List[FundamentalSnapshot]]]:
    tickers = ["AAPL", "MSFT", "GOOGL"]
    spy_symbol = "SPY"
    finnhub_key = os.environ.get("FINNHUB_API_KEY")
    start_year = int(start_date[:4])
    end_year = int(end_date[:4])

    if finnhub_key:
        fundamentals_source = FinnhubFundamentalsSource(finnhub_key, symbols=tickers)
        fundamentals_raw = fundamentals_source.all_fundamentals()
    else:
        fundamentals_raw = _fundamentals(tickers, start_year, end_year)
        fundamentals_source = InMemorySource({}, fundamentals_raw, {}, {})

    membership = {"SP500": {str(year): tickers for year in range(start_year, end_year + 1)}}
    price_history = {
        symbol: _price_series(symbol, start_date, end_date) for symbol in tickers + [spy_symbol]
    }
    dates = [bar.date for bar in price_history[spy_symbol]]
    fx_history = {"USDPLN": [PriceBar(date, 4.0) for date in dates]}

    misc_source = InMemorySource(price_history, fundamentals_raw, membership, fx_history)
    loader = DataLoader(
        price_source=misc_source,
        fundamentals_source=fundamentals_source,
        membership_source=misc_source,
        fx_source=misc_source,
    )
    return loader, tickers, fundamentals_raw


def _collect_coverage(loader: DataLoader, symbols: List[str]) -> CoverageResult:
    coverage: Dict[Tuple[str, str], Dict[str, bool]] = {}
    periods: set = set()

    for symbol in symbols:
        try:
            snapshots = loader.load_fundamentals(symbol)
        except URLError as exc:
            print(f"HTTP error for {symbol}: {exc}")
            continue
        except Exception as exc:  # pragma: no cover - defensive
            print(f"Error loading fundamentals for {symbol}: {exc}")
            continue

        for snap in snapshots:
            period = str(snap.period)
            periods.add(period)
            status: Dict[str, bool] = {}
            for key in METRICS:
                value = snap.metrics.get(key)
                status[key] = value is not None
            coverage[(symbol, period)] = status
    return CoverageResult(coverage=coverage, symbols=symbols, periods=sorted(periods))


def _metric_completeness(result: CoverageResult) -> Dict[str, float]:
    totals = {key: 0 for key in METRICS}
    total_snaps = len(result.coverage)
    if total_snaps == 0:
        return {key: 0.0 for key in METRICS}

    for snapshot_flags in result.coverage.values():
        for key, present in snapshot_flags.items():
            totals[key] += 1 if present else 0
    return {key: totals[key] / total_snaps * 100.0 for key in METRICS}


def _period_completeness(result: CoverageResult) -> Dict[str, float]:
    if not result.coverage:
        return {}
    per_period: Dict[str, List[float]] = defaultdict(list)
    for (symbol, period), flags in result.coverage.items():
        present = sum(1 for v in flags.values() if v)
        per_period[period].append(present / len(METRICS) * 100.0)
    return {period: mean(vals) for period, vals in sorted(per_period.items())}


def _symbol_missing_counts(result: CoverageResult) -> Dict[str, int]:
    counts: Dict[str, int] = defaultdict(int)
    for (symbol, _), flags in result.coverage.items():
        missing = len([k for k, v in flags.items() if not v])
        counts[symbol] += missing
    return counts


def _snapshot_scores(result: CoverageResult) -> List[Tuple[str, str, int]]:
    scores: List[Tuple[str, str, int]] = []
    for (symbol, period), flags in result.coverage.items():
        scores.append((symbol, period, sum(1 for v in flags.values() if v)))
    return sorted(scores, key=lambda x: x[2])


def _missing_metrics(flags: Dict[str, bool]) -> List[str]:
    return [k for k, present in flags.items() if not present]


def _print_report(result: CoverageResult) -> None:
    total_snaps = len(result.coverage)
    if total_snaps == 0:
        print("No fundamentals found")
        return

    metrics_pct = _metric_completeness(result)
    period_pct = _period_completeness(result)
    missing_counts = _symbol_missing_counts(result)
    snapshot_scores = _snapshot_scores(result)

    periods_sorted = sorted({p for _, p in result.coverage.keys()})
    period_range = f"{periods_sorted[0]}–{periods_sorted[-1]}" if periods_sorted else "n/a"

    print("================= FUNDAMENTAL COVERAGE REPORT =================")
    print(f"Snapshots total: {total_snaps}")
    print(f"Symbols: {len(result.symbols)}")
    print(f"Periods: {period_range}")
    print("")
    print("Metric completeness:")
    for key in METRICS:
        pct = metrics_pct.get(key, 0.0)
        warning = " [WARNING: LOW COVERAGE]" if pct < 60.0 else ""
        print(f"{key.ljust(30,'.')} {pct:.1f}%{warning}")
    print("")
    print("Coverage by period:")
    for period, pct in period_pct.items():
        print(f"{period}: {pct:.1f}%")
    print("")
    worst_symbols = sorted(missing_counts.items(), key=lambda t: t[1], reverse=True)[:5]
    print("Worst symbols (most missing fields):")
    for symbol, missing in worst_symbols:
        print(f"{symbol}: missing {missing} fields")
    print("")

    best = snapshot_scores[-5:][::-1]
    worst = snapshot_scores[:5]
    print("Best snapshots:")
    for symbol, period, count in best:
        missing = _missing_metrics(result.coverage[(symbol, period)])
        print(f"{symbol} {period}: {count}/{len(METRICS)} present | missing: {', '.join(missing) if missing else 'none'}")
    print("")
    print("Worst snapshots:")
    for symbol, period, count in worst:
        missing = _missing_metrics(result.coverage[(symbol, period)])
        print(f"{symbol} {period}: {count}/{len(METRICS)} present | missing: {', '.join(missing) if missing else 'none'}")
    print("===============================================================")


def main() -> None:
    start_date = "2000-01-01"
    end_date = "2025-01-01"

    loader, symbols, _ = _build_loader(start_date, end_date)

    # Ensure the same scoring path is initialized (for side effects that may enrich metrics)
    strategy_cfg = StrategyConfig(
        backtest=BacktestConfig(start_date=start_date, end_date=end_date, base_currency="PLN", initial_capital=100000)
    )
    UniverseBuilder(loader)  # instantiated to mirror backtest setup
    scorer = FundamentalScorer(
        ScoringRules(
            quality=quality_score,
            value=lambda snap: max(0.0, 100.0 - snap.metrics.get("pe", 0)),
            growth=growth_score,
            moat=moat_score,
            risk=lambda snap: max(0.0, 100.0 - snap.metrics.get("volatility", 0)),
        )
    )
    # Trigger scoring to ensure any derived metrics paths remain intact
    for symbol in symbols:
        try:
            scorer.score(symbol, loader.load_fundamentals(symbol))
        except Exception:
            # Coverage inspection should continue even if scoring fails for a symbol
            continue

    result = _collect_coverage(loader, symbols)
    _print_report(result)


if __name__ == "__main__":
    main()
