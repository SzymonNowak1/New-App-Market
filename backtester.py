"""Convenience runner for the Buffett/Lynch 2.0 backtest using Yahoo Finance data."""
from __future__ import annotations

from datetime import datetime
import hashlib
from pathlib import Path
from typing import Dict, List

import numpy as np
import pandas as pd
import yfinance as yf

from buffett_lynch.backtester import Backtester
from buffett_lynch.config import BacktestConfig, StrategyConfig
from buffett_lynch.currency_engine import CurrencyEngine
from buffett_lynch.data_loader import DataLoader, InMemorySource
from buffett_lynch.execution_engine import ExecutionEngine
from buffett_lynch.fundamental_scoring import (
    FundamentalScorer,
    ScoringRules,
    growth_score,
    moat_score,
    quality_score,
)
from buffett_lynch.models import FundamentalSnapshot, PriceBar
from buffett_lynch.portfolio_manager import PortfolioManager
from buffett_lynch.universe_builder import UniverseBuilder


def _price_series(symbol: str, start_date: str, end_date: str) -> List[PriceBar]:
    """Download price history for a symbol with a deterministic fallback."""
    df = yf.download(symbol, start=start_date, end=end_date, auto_adjust=True, progress=False)
    if df.empty:
        dates = pd.date_range(start=start_date, end=end_date, freq="B")
        prices = pd.Series(np.linspace(100, 120, len(dates)), index=dates)
    else:
        prices = df["Close"]

    # yfinance can return a DataFrame for `Close` when column indices carry ticker labels;
    # convert to a single Series before iterating to avoid interpreting ticker names as dates.
    if isinstance(prices, pd.DataFrame):
        if prices.shape[1] == 1:
            prices = prices.iloc[:, 0]
        else:
            col = symbol if symbol in prices.columns else prices.columns[0]
            prices = prices[col]

    return [PriceBar(pd.to_datetime(date).strftime("%Y-%m-%d"), float(price)) for date, price in prices.items()]


def _fundamentals(symbols: List[str], start_year: int, end_year: int) -> Dict[str, List[FundamentalSnapshot]]:
    """Synthesize fundamental snapshots with moat-ready raw inputs.

    The Yahoo Finance metadata can be sparse; we synthesize deterministic values
    with a small symbol-specific jitter to avoid identical scores. Percentiles
    are computed later by the data loading layer so this helper only provides
    the raw inputs (gross margin %, R&D/Sales %, ROIC trend proxy, etc.).
    """

    def _with_jitter(base: float, symbol: str, scale: float = 0.02) -> float:
        """Deterministically vary fallback values so percentiles are meaningful."""

        digest = hashlib.sha256(symbol.encode()).digest()
        bucket = digest[0] % 5
        return base * (1 + bucket * scale)

    raw_metrics: Dict[str, Dict[str, float]] = {}
    meta: Dict[str, Dict[str, float]] = {}
    for symbol in symbols:
        info = yf.Ticker(symbol).info or {}
        market_cap = float(info.get("marketCap") or 1e10)
        sector = info.get("sector") or "Unknown"
        roe = float(info.get("returnOnEquity") or 15.0)
        pe = float(info.get("trailingPE") or 18.0)
        growth = float(info.get("revenueGrowth") or 0.08) * 100
        volatility = float(info.get("beta") or 1.1) * 20

        gross_margin_pct = info.get("grossMargins")
        if gross_margin_pct is not None:
            gross_margin_pct = float(gross_margin_pct) * 100
        else:
            gross_margin_pct = _with_jitter(40.0, symbol)

        rd_expense = info.get("researchDevelopment")
        revenue = info.get("totalRevenue")
        if rd_expense is not None and revenue:
            rd_sales_pct = float(rd_expense) / float(revenue) * 100
        else:
            rd_sales_pct = _with_jitter(8.0, symbol)

        roic_trend_pct = info.get("returnOnEquity")
        if roic_trend_pct is not None:
            roic_trend_pct = float(roic_trend_pct) * 10
        else:
            roic_trend_pct = _with_jitter(10.0, symbol)

        revenue_volatility_penalty = max(0.0, volatility * 0.2)

        raw_metrics[symbol] = {
            "roe": roe,
            "pe": pe,
            "growth": growth,
            "volatility": volatility,
            "gross_margin_pct": gross_margin_pct,
            "rd_sales_pct": rd_sales_pct,
            "roic_trend_pct": roic_trend_pct,
            "revenue_volatility_penalty": revenue_volatility_penalty,
        }
        meta[symbol] = {"market_cap": market_cap, "sector": sector}

    moat_percentile_sources = {
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

    per_year_values: Dict[str, Dict[str, List[float]]] = {
        str(year): {source: [] for source in moat_percentile_sources.values()}
        for year in range(start_year, end_year + 1)
    }

    for metrics in raw_metrics.values():
        for source_key in moat_percentile_sources.values():
            value = metrics.get(source_key)
            for year in per_year_values.keys():
                if value is not None:
                    per_year_values[year][source_key].append(value)

    medians: Dict[str, Dict[str, float]] = {}
    for year, metrics in per_year_values.items():
        medians[year] = {source_key: _median(values) for source_key, values in metrics.items()}

    peers: Dict[str, Dict[str, List[float]]] = {
        year: {source_key: [] for source_key in moat_percentile_sources.values()}
        for year in per_year_values.keys()
    }

    for metrics in raw_metrics.values():
        for year in peers.keys():
            for source_key in moat_percentile_sources.values():
                fallback = medians[year][source_key]
                value = metrics.get(source_key, fallback)
                peers[year][source_key].append(value if value is not None else fallback)

    fundamentals: Dict[str, List[FundamentalSnapshot]] = {}
    for symbol, metrics in raw_metrics.items():
        for year in range(start_year, end_year + 1):
            metrics_with_moat = dict(metrics)
            for output_key, source_key in moat_percentile_sources.items():
                fallback = medians[str(year)][source_key]
                value = metrics_with_moat.get(source_key, fallback)
                percentile = _percentile_rank(value if value is not None else fallback, peers[str(year)][source_key])
                metrics_with_moat[output_key] = percentile
            fundamentals.setdefault(symbol, []).append(
                FundamentalSnapshot(
                    period=str(year),
                    market_cap=meta[symbol]["market_cap"],
                    sector=meta[symbol]["sector"],
                    metrics=metrics_with_moat,
                )
            )
    return fundamentals


def run_backtest(start_date: str, end_date: str, initial_capital: float, base_currency: str = "PLN"):
    """Fetch data, run the Buffett/Lynch backtest, and write an equity curve to reports/."""
    Path("reports").mkdir(exist_ok=True)

    tickers = ["AAPL", "MSFT", "GOOGL"]
    spy_symbol = "SPY"

    start_year = datetime.fromisoformat(start_date).year
    end_year = datetime.fromisoformat(end_date).year
    fundamentals_raw = _fundamentals(tickers, start_year, end_year)

    membership = {"SP500": {str(year): tickers for year in range(start_year, end_year + 1)}}

    strategy_cfg = StrategyConfig(
        backtest=BacktestConfig(
            start_date=start_date,
            end_date=end_date,
            base_currency=base_currency,
            initial_capital=initial_capital,
        )
    )
    execution = ExecutionEngine(strategy_cfg.portfolio)
    bear_symbol, bear_currency = execution.bear_asset(strategy_cfg.backtest.base_currency)
    bear_tickers = [bear_symbol]

    price_history: Dict[str, List[PriceBar]] = {
        symbol: _price_series(symbol, start_date, end_date)
        for symbol in tickers + bear_tickers + [spy_symbol]
    }
    spy_prices = price_history.pop(spy_symbol)
    dates = [bar.date for bar in spy_prices]
    # Flat FX history so portfolio conversion always succeeds
    fx_history = {
        f"USD{base_currency}": [PriceBar(date, 4.0) for date in dates],
        f"EUR{base_currency}": [PriceBar(date, 4.3) for date in dates],
    }

    rules = ScoringRules(
        quality=quality_score,
        value=lambda snap: max(0.0, 100.0 - snap.metrics.get("pe", 0)),
        growth=growth_score,
        moat=moat_score,
        risk=lambda snap: max(0.0, 100.0 - snap.metrics.get("volatility", 0)),
    )

    source = InMemorySource(price_history, fundamentals_raw, membership, fx_history)
    loader = DataLoader(source, source, source, source)
    scorer = FundamentalScorer(rules)
    scored_fundamentals = {
        symbol: scorer.score(symbol, loader.load_fundamentals(symbol))
        for symbol in fundamentals_raw.keys()
    }

    universe = UniverseBuilder(loader)
    portfolio_manager = PortfolioManager(strategy_cfg.portfolio, strategy_cfg.rebalancing)
    currency = CurrencyEngine(strategy_cfg.backtest.base_currency)
    backtester = Backtester(universe, scorer, portfolio_manager, execution, currency, strategy_cfg.backtest)

    top100 = universe.build_top_market_cap("SP500")
    report = backtester.run(spy_prices, price_history, scored_fundamentals, top100, fx_history)

    equity_df = pd.DataFrame(report.equity_curve, columns=["date", "equity_pln"])
    equity_df.to_csv("reports/equity_curve.csv", index=False)

    # Persist and display the analyzed period for visibility in CI logs and artifacts
    summary_path = Path("reports/backtest_summary.txt")
    summary_path.write_text(f"Analyzed period: {start_date} → {end_date}\n")

    print("Backtest complete")
    print(f"Analyzed period: {start_date} → {end_date}")
    print(f"CAGR: {report.cagr:.2%}")
    print(f"Max Drawdown: {report.max_drawdown:.2%}")
    print(f"Sharpe: {report.sharpe:.2f}")
    print(f"Transactions: {report.transactions}")
    print(f"Average holding days: {report.avg_holding_days:.1f}")
    print(f"Bull exposure: {report.bull_exposure:.2%} | Bear exposure: {report.bear_exposure:.2%}")

    return report


__all__ = ["run_backtest"]
