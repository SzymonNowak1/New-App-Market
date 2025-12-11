from buffett_lynch.finnhub_fundamentals import FinnhubFundamentalsSource
from buffett_lynch.data_loader import DataLoader
from buffett_lynch.universe_builder import UniverseBuilder
from buffett_lynch.dummy_membership_source import DummyIndexMembershipSource


FINNHUB_API_KEY = "TU_WSTAW_SWÓJ_KLUCZ"   # ← wstaw swój API KEY


def build_data_sources():
    """
    Tworzy pełny zestaw źródeł danych do backtestu/debugowania.
    Wersja z DummyIndexMembershipSource działa, dopóki nie dodamy
    realnych składów S&P500.
    """

    fundamentals_source = FinnhubFundamentalsSource(
        api_key=FINNHUB_API_KEY,
        symbols=["AAPL", "MSFT", "GOOGL", "AMZN", "META"]   # przykładowe symbole
    )

    membership_source = DummyIndexMembershipSource(fundamentals_source)

    loader = DataLoader(
        price_source=fundamentals_source,
        fundamentals_source=fundamentals_source,
        membership_source=membership_source,
        fx_source=fundamentals_source,
    )

    universe = UniverseBuilder(loader)

    return loader, universe
