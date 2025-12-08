"""FX conversion utilities."""
from __future__ import annotations

from typing import Dict, List

from .models import PriceBar
from .execution_engine import sma


class CurrencyEngine:
    def __init__(self, base_currency: str = "PLN"):
        self.base_currency = base_currency

    def fx_to_pln(self, fx_history: Dict[str, List[PriceBar]], date: str, currency: str) -> float:
        pair = f"{currency}{self.base_currency}"
        history = fx_history.get(pair, [])
        for bar in history:
            if bar.date == date:
                return bar.close
        return 1.0 if currency == self.base_currency else 0.0

    def portfolio_to_pln(self, holdings: Dict[str, float], fx_history: Dict[str, List[PriceBar]], date: str,
                          currency_map: Dict[str, str]) -> float:
        total = 0.0
        for symbol, value in holdings.items():
            currency = currency_map.get(symbol, self.base_currency)
            rate = self.fx_to_pln(fx_history, date, currency)
            total += value * rate
        return total


__all__ = ["CurrencyEngine"]

