"""Entrypoint for running the Buffett/Lynch 2.0 backtest via CLI or CI."""

from pathlib import Path
import sys


# Ensure repository root is on the import path so `backtester.py` is importable
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


from backtester import run_backtest

if __name__ == "__main__":
    run_backtest(
        start_date="2000-01-01",
        end_date="2025-01-01",
        initial_capital=100000,  # przykładowa wartość
        base_currency="PLN",
    )
