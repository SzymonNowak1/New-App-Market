from buffett_lynch.finnhub_fundamentals import FinnhubFundamentals
from buffett_lynch.data_loader import DataLoader
from buffett_lynch.universe_builder import UniverseBuilder


def build_data_sources():
    """
    Helper used by debugging scripts. Creates Finnhub fundamentals loader
    and wraps it into a DataLoader + UniverseBuilder.
    """
    fundamentals_source = FinnhubFundamentals()
    
    loader = DataLoader(
        price_source=fundamentals_source,
        fundamentals_source=fundamentals_source,
        membership_source=fundamentals_source,
        fx_source=fundamentals_source,
    )

    universe = UniverseBuilder(loader)
    return loader, universe
