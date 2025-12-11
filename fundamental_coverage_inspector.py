import json
import os
import sys
from collections import Counter, defaultdict
from typing import Dict, List, Tuple
from urllib import parse, request, error


SYMBOLS = ["AAPL", "MSFT", "AMZN", "META", "TSLA", "JNJ", "GE", "IBM", "ORCL", "XOM"]
YEARS = [2000, 2005, 2010, 2015, 2020, 2024]
METRICS = [
    "revenue",
    "gross_profit",
    "r_and_d_expense",
    "roic_inputs",
    "sector",
    "market_cap",
]
BASE_URL = "https://finnhub.io/api/v1"


def _fetch_json(path: str, params: Dict[str, str], api_key: str) -> Dict:
    query = parse.urlencode({**params, "token": api_key})
    url = f"{BASE_URL}{path}?{query}"
    try:
        with request.urlopen(url, timeout=15) as resp:  # type: ignore[arg-type]
            data = resp.read()
            return json.loads(data.decode("utf-8"))
    except error.HTTPError as exc:  # pragma: no cover - network dependent
        print(f"[WARN] HTTP error for {url}: {exc}", file=sys.stderr)
    except error.URLError as exc:  # pragma: no cover - network dependent
        print(f"[WARN] URL error for {url}: {exc}", file=sys.stderr)
    except Exception as exc:  # pragma: no cover - defensive
        print(f"[WARN] Failed to fetch {url}: {exc}", file=sys.stderr)
    return {}


def _extract_year(entry: Dict) -> int:
    for key in ("year", "period", "fiscalYear", "endDate"):
        value = entry.get(key)
        if isinstance(value, int):
            return value
        if isinstance(value, str) and len(value) >= 4 and value[:4].isdigit():
            return int(value[:4])
    return -1


def _extract_report_values(entry: Dict) -> Dict[str, float]:
    values: Dict[str, float] = {}
    report = entry.get("report", {})
    for section in report.values():
        if not isinstance(section, list):
            continue
        for item in section:
            val = item.get("value")
            if val is None:
                continue
            for key in (item.get("concept"), item.get("label")):
                if key:
                    values[key.lower()] = val
    return values


def _first_match(values: Dict[str, float], candidates: List[str]) -> bool:
    for key in values:
        for candidate in candidates:
            if candidate in key:
                return True
    return False


def _collect_symbol_year_metrics(api_key: str, symbol: str) -> Dict[int, Dict[str, bool]]:
    coverage: Dict[int, Dict[str, bool]] = {year: {metric: False for metric in METRICS} for year in YEARS}

    financials = _fetch_json("/stock/financials-reported", {"symbol": symbol, "freq": "annual"}, api_key)
    metrics_data = _fetch_json("/stock/metric", {"symbol": symbol, "metric": "all"}, api_key)
    profile_data = _fetch_json("/stock/profile2", {"symbol": symbol}, api_key)

    metric_map: Dict[int, Dict[str, float]] = {}
    if isinstance(financials, dict):
        for entry in financials.get("data", []) or []:
            year = _extract_year(entry)
            if year == -1:
                continue
            metric_map[year] = _extract_report_values(entry)

    sector_present = bool(profile_data.get("finnhubIndustry") or metrics_data.get("metric", {}).get("sector"))
    market_cap_present = bool(metrics_data.get("metric", {}).get("marketCapitalization"))

    for year in YEARS:
        year_vals = metric_map.get(year, {})
        has_revenue = _first_match(year_vals, ["revenue"])
        has_gross = _first_match(year_vals, ["grossprofit", "gross profit", "gross"])
        has_rnd = _first_match(year_vals, ["research", "r&d", "rnd", "r and d"])
        has_operating = _first_match(year_vals, ["operatingincome", "operating income", "ebit"])
        has_debt = _first_match(year_vals, ["totaldebt", "longtermdebt", "debt"])
        has_assets = _first_match(year_vals, ["totalassets", "investedcapital", "total asset", "invested capital"])

        coverage[year]["revenue"] = has_revenue
        coverage[year]["gross_profit"] = has_gross
        coverage[year]["r_and_d_expense"] = has_rnd
        coverage[year]["roic_inputs"] = has_operating and (has_assets or has_debt)
        coverage[year]["sector"] = sector_present
        coverage[year]["market_cap"] = market_cap_present

    return coverage


def compute_completeness(coverage: Dict[str, Dict[int, Dict[str, bool]]]) -> Tuple[float, Dict[str, float], Dict[int, float], Dict[str, float]]:
    total_combinations = len(SYMBOLS) * len(YEARS)
    total_entries = total_combinations * len(METRICS)

    metric_counts: Counter = Counter()
    year_counts: Counter = Counter()
    symbol_counts: Counter = Counter()

    for symbol, year_map in coverage.items():
        for year, metrics in year_map.items():
            for metric, present in metrics.items():
                if present:
                    metric_counts[metric] += 1
                    year_counts[year] += 1
                    symbol_counts[symbol] += 1

    overall = (sum(metric_counts.values()) / total_entries * 100) if total_entries else 0.0
    metric_pct = {metric: (metric_counts.get(metric, 0) / total_combinations * 100) for metric in METRICS}
    year_pct = {year: (year_counts.get(year, 0) / (len(SYMBOLS) * len(METRICS)) * 100) for year in YEARS}
    symbol_pct = {symbol: (symbol_counts.get(symbol, 0) / (len(YEARS) * len(METRICS)) * 100) for symbol in SYMBOLS}
    return overall, metric_pct, year_pct, symbol_pct


def _build_missing_maps(coverage: Dict[str, Dict[int, Dict[str, bool]]]):
    missing_by_symbol: Dict[str, Dict[str, List[int]]] = {sym: defaultdict(list) for sym in SYMBOLS}
    missing_by_year: Dict[int, Dict[str, List[str]]] = {year: defaultdict(list) for year in YEARS}

    for symbol, years_map in coverage.items():
        for year, metrics in years_map.items():
            for metric, present in metrics.items():
                if not present:
                    missing_by_symbol[symbol][metric].append(year)
                    missing_by_year[year][metric].append(symbol)
    return missing_by_symbol, missing_by_year


def _worst_offenders(symbol_pct: Dict[str, float], missing_by_symbol: Dict[str, Dict[str, List[int]]]) -> List[str]:
    ranked = sorted(SYMBOLS, key=lambda s: symbol_pct.get(s, 0))
    lines: List[str] = []
    for symbol in ranked[:3]:
        gaps = []
        for metric, years in sorted(missing_by_symbol[symbol].items()):
            if years:
                years_str = ",".join(str(y) for y in sorted(set(years)))
                gaps.append(f"{metric}({years_str})")
        missing_str = ", ".join(gaps) if gaps else "no gaps"
        lines.append(f"{symbol}: missing {missing_str}")
    return lines


def _format_metric_line(name: str, pct: float) -> str:
    dots = "." * max(1, 23 - len(name))
    line = f"{name}{dots} {pct:0.1f}%"
    if pct < 60.0:
        line += "  [WARNING: LOW COVERAGE]"
    return line


def print_report(overall: float, metric_pct: Dict[str, float], year_pct: Dict[int, float], offenders: List[str]) -> None:
    total_combinations = len(SYMBOLS) * len(YEARS)
    print("================= FUNDAMENTAL COVERAGE REPORT =================")
    print(f"Years tested: {', '.join(str(y) for y in YEARS)}")
    print(f"Symbols tested: {len(SYMBOLS)}")
    print(f"Overall dataset completeness: {overall:0.1f}%")
    print(f"Total combinations: {total_combinations}")
    print()
    print("Metric completeness:")
    for metric in METRICS:
        print(_format_metric_line(metric, metric_pct.get(metric, 0.0)))
    print()
    print("Coverage by year:")
    for year in YEARS:
        print(f"{year}: {year_pct.get(year, 0.0):0.1f}%")
    print()
    print("Worst symbols:")
    for line in offenders:
        print(line)
    print("===============================================================")


def main() -> None:
    api_key = os.environ.get("FINNHUB_API_KEY")
    if not api_key:
        print("FINNHUB_API_KEY not set; cannot inspect coverage.", file=sys.stderr)
        sys.exit(1)

    coverage: Dict[str, Dict[int, Dict[str, bool]]] = {}
    for symbol in SYMBOLS:
        coverage[symbol] = _collect_symbol_year_metrics(api_key, symbol)

    overall, metric_pct, year_pct, symbol_pct = compute_completeness(coverage)
    missing_by_symbol, _missing_by_year = _build_missing_maps(coverage)
    offenders = _worst_offenders(symbol_pct, missing_by_symbol)

    print_report(overall, metric_pct, year_pct, offenders)


if __name__ == "__main__":
    main()
