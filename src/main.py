from backtester import run_backtest

if __name__ == "__main__":
    run_backtest(
        start_date="2000-01-01",
        end_date="2025-01-01",
        initial_capital=100000,  # przykładowa wartość
        base_currency="PLN",
    )
