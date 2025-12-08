"""Ensure FundamentalSnapshot construction includes moat percentile metrics."""

import sys
import types
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import backtester as runner


class _StubTicker:
    def __init__(self, info):
        self.info = info


def _stub_yf(mapping):
    stub = types.SimpleNamespace()
    stub.Ticker = lambda symbol: _StubTicker(mapping.get(symbol, {}))
    return stub


def test_moat_percentiles_populated(monkeypatch):
    fundamentals_data = {
        "AAA": {
            "grossMargins": 0.55,
            "researchDevelopment": 5,
            "totalRevenue": 100,
            "returnOnEquity": 0.15,
            "marketCap": 1e11,
            "sector": "Tech",
        },
        "BBB": {
            "grossMargins": 0.35,
            "researchDevelopment": 2,
            "totalRevenue": 100,
            "returnOnEquity": 0.09,
            "marketCap": 9e10,
            "sector": "Health",
        },
        # Missing values should fall back to the universe median, not a fixed 0.5 percentile.
        "CCC": {
            "grossMargins": None,
            "researchDevelopment": None,
            "totalRevenue": None,
            "returnOnEquity": None,
            "marketCap": 8e10,
            "sector": "Energy",
        },
    }

    monkeypatch.setattr(runner, "yf", _stub_yf(fundamentals_data))

    fundamentals = runner._fundamentals(list(fundamentals_data.keys()), 2020, 2020)

    moat_components = {"gross_margin_percentile", "r_and_d_to_sales_percentile", "roic_trend_percentile"}

    percentiles = {metric: [] for metric in moat_components}

    for symbol, snapshots in fundamentals.items():
        snap = snapshots[0]
        for metric in moat_components:
            assert metric in snap.metrics
            percentiles[metric].append(snap.metrics[metric])

    # Each percentile vector should vary by symbol and stay within 0-100 bounds.
    for values in percentiles.values():
        assert all(0.0 <= v <= 100.0 for v in values)
        assert len(set(np.round(values, 6))) > 1
