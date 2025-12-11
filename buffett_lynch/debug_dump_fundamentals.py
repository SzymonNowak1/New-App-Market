from buffett_lynch.data_loader import DataLoader
from buffett_lynch.universe_builder import UniverseBuilder
from buffett_lynch.main import build_data_sources


def main() -> None:
    print("========== FUNDAMENTAL DEBUG DUMP ==========")

    # 🔹 importujemy to samo, co używa Twój main do zbudowania DataLoadera
    # jeśli w main.py jest inna funkcja budująca loader, tutaj tylko zmienimy nazwę
    try:
        from .main import build_data_sources  # dopasujemy nazwę jeśli będzie błąd
    except ImportError:
        print("Nie mogę zaimportować build_data_sources z main.py")
        print("Pokaż mi proszę zawartość src/main.py w czacie, to dopasujemy nazwę funkcji.")
        return

    loader, universe_builder = build_data_sources()

    # 🔹 bierzemy ten sam indeks, którego używa backtest – dopasuj jeśli u Ciebie jest inny
    universe = universe_builder.build_top_market_cap("SP500")

    years = sorted(universe.keys())
    if not years:
        print("Brak danych wszechświata (universe).")
        return

    first_year = years[0]
    sample_symbols = universe[first_year][:5]

    print(f"Inspecting year {first_year} sample: {sample_symbols}")

    for symbol in sample_symbols:
        print("\n------", symbol, "------")
        fundamentals = loader.load_fundamentals(symbol)
        if not fundamentals:
            print("  (brak fundamentów)")
            continue
        for snap in fundamentals:
            print(f"[{snap.period}] market_cap={snap.market_cap}")
            print("metrics:")
            if not snap.metrics:
                print("   (pusty metrics)")
            for k, v in snap.metrics.items():
                print("   ", k, "=", v)

    print("\n=============================================")


if __name__ == "__main__":
    main()
