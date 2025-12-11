from src.data_loader import DataLoader
from src.universe_builder import UniverseBuilder


def main():
    print("========== FUNDAMENTAL DEBUG DUMP ==========")

    # Build loader exactly like main.py
    from src.main import build_data_sources  # adjust if your main file differs
    loader = build_data_sources()

    universe_builder = UniverseBuilder(loader)
    universe = universe_builder.build_top_market_cap("SP500")  # or your index

    # We take only first 5 tickers from 2000 for inspection
    years = sorted(universe.keys())
    first_year = years[0]
    sample_symbols = universe[first_year][:5]

    print(f"Inspecting year {first_year} sample: {sample_symbols}")

    for symbol in sample_symbols:
        print("\n------", symbol, "------")
        fundamentals = loader.load_fundamentals(symbol)
        for snap in fundamentals:
            print(f"[{snap.period}] market_cap={snap.market_cap}")
            print("metrics:")
            for k, v in snap.metrics.items():
                print("   ", k, "=", v)

    print("\n=============================================")


if __name__ == "__main__":
    main()
