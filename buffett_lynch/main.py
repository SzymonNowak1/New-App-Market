"""Entrypoint and data-source builder for Buffett/Lynch 2.0."""

from pathlib import Path
import sys

# make repo importable when run as script
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
        symbols=None  # let it load as needed
    )

    loader = DataLoader(
        price_source=fundamentals_source,          # tymczasowo brak osobnego źródła cen
        fundamentals_source=fundamentals_source,
        membership_source=fundamentals_source,     # Finnhub też dostarcza skład indeksów
        fx_source=fundamentals_source,             # oraz kursy
