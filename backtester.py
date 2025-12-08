"""Convenience runner for the Buffett/Lynch 2.0 backtest using Yahoo Finance data."""
from __future__ import annotations

from datetime import datetime
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
    fundamentals: Dict[str, List[FundamentalSnapshot]] = {}
    for symbol in symbols:
        info = yf.Ticker(symbol).info or {}
        market_cap = float(info.get("marketCap") or 1e10)
        sector = info.get("sector") or "Unknown"
        roe = float(info.get("returnOnEquity") or 15.0)
        pe = float(info.get("trailingPE") or 18.0)
        growth = float(info.get("revenueGrowth") or 0.08) * 100
        volatility = float(info.get("beta") or 1.1) * 20
        gross_margin_pct = float(info.get("grossMargins") or 0.40) * 100
        rd_sales_pct = float(info.get("researchDevelopment") or 0.08) * 100
        roic_trend_pct = float(info.get("returnOnEquity") or 0.10) * 10
        revenue_volatility_penalty = max(0.0, volatility * 0.2)
        metrics = {
            "roe": roe,
            "pe": pe,
            "growth": growth,
            "volatility": volatility,
            "gross_margin_pct": gross_margin_pct,
            "rd_sales_pct": rd_sales_pct,
            "roic_trend_pct": roic_trend_pct,
            "revenue_volatility_penalty": revenue_volatility_penalty,
        }
        for year in range(start_year, end_year + 1):
            fundamentals.setdefault(symbol, []).append(
                FundamentalSnapshot(period=str(year), market_cap=market_cap, sector=sector, metrics=metrics)
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

    # Flat FX history so portfolio conversion always succeeds
    dates = [bar.date for bar in spy_prices]
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
    scored_fundamentals = {symbol: scorer.score(symbol, snaps) for symbol, snaps in fundamentals_raw.items()}

    strategy_cfg = StrategyConfig(
        backtest=BacktestConfig(
            start_date=start_date,
            end_date=end_date,
            base_currency=base_currency,
            initial_capital=initial_capital,
        )
    )
    universe = UniverseBuilder(loader)
    portfolio_manager = PortfolioManager(strategy_cfg.portfolio, strategy_cfg.rebalancing)
    execution = ExecutionEngine(strategy_cfg.portfolio)
    bear_symbol, bear_currency = execution.bear_asset(strategy_cfg.backtest.base_currency)
    bear_tickers = [bear_symbol]

    price_history: Dict[str, List[PriceBar]] = {
        symbol: _price_series(symbol, start_date, end_date)
        for symbol in tickers + bear_tickers + [spy_symbol]
    }
    spy_prices = price_history.pop(spy_symbol)
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
