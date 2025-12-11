"""Entrypoint and data-source builder for Buffett/Lynch 2.0."""

from pathlib import Path
import sys

# Ensure repository root is on import path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from buffett_lynch.finnhub_fundamentals import FinnhubFundamentalsSource
from buffett_lynch.data_loader import DataLoader
from buffett_lynch.universe_builder import UniverseBuilder


def build_data_sources():
    """
    Creates Finnhub-backed data sources for debugging + backtests.
    """

    API_KEY = "d4rjk21r01qgts2oha6gd4rjk21r01qgts2oha70"

    fundamentals_source = FinnhubFundamentalsSource(
        api_key=API_KEY,
        symbols=None
    )

    loader = DataLoader(
        price_source=fundamentals_source,
        fundamentals_source=fundamentals_source,
        membership_source=fundamentals_source,
        fx_source=fundamentals_source,
    )

    universe = UniverseBuilder(loader)
    return loader, universe


if __name__ == "__main__":
    from buffett_lynch.backtester import run_backtest

    run_backtest(
        start_date="2000-01-01",
        end_date="2025-01-01",
        initial_capital=100000,
        base_currency="PLN",
    )
