"""Data access layer for prices, fundamentals, index membership, and FX."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Protocol

from .models import FundamentalSnapshot, PriceBar


class PriceDataSource(Protocol):
    def price_history(self, symbol: str) -> List[PriceBar]:
        ...


class FundamentalsDataSource(Protocol):
    def fundamentals(self, symbol: str) -> List[FundamentalSnapshot]:
        ...


class IndexMembershipSource(Protocol):
    def members(self, index: str) -> Dict[str, List[str]]:
        """Return mapping year -> symbols that belong to the index."""
        ...


class FXRateSource(Protocol):
    def history(self, pair: str) -> List[PriceBar]:
        ...


@dataclass
class DataLoader:
    price_source: PriceDataSource
    fundamentals_source: FundamentalsDataSource
    membership_source: IndexMembershipSource
    fx_source: FXRateSource

    def load_price_history(self, symbol: str) -> List[PriceBar]:
        return sorted(self.price_source.price_history(symbol), key=lambda b: b.date)

    def load_fundamentals(self, symbol: str) -> List[FundamentalSnapshot]:
        return sorted(self.fundamentals_source.fundamentals(symbol), key=lambda f: f.period)

    def load_index_members(self, index: str) -> Dict[str, List[str]]:
        return self.membership_source.members(index)

    def load_fx_history(self, pair: str) -> List[PriceBar]:
        return sorted(self.fx_source.history(pair), key=lambda b: b.date)


class InMemorySource(PriceDataSource, FundamentalsDataSource, IndexMembershipSource, FXRateSource):
    """A simple in-memory provider useful for tests or backtests."""

    def __init__(self, prices: Dict[str, List[PriceBar]], fundamentals: Dict[str, List[FundamentalSnapshot]],
                 membership: Dict[str, Dict[str, List[str]]], fx: Dict[str, List[PriceBar]]):
        self._prices = prices
        self._fundamentals = fundamentals
        self._membership = membership
        self._fx = fx

    def price_history(self, symbol: str) -> List[PriceBar]:
        return self._prices.get(symbol, [])

    def fundamentals(self, symbol: str) -> List[FundamentalSnapshot]:
        return self._fundamentals.get(symbol, [])

    def members(self, index: str) -> Dict[str, List[str]]:
        return self._membership.get(index, {})

    def history(self, pair: str) -> List[PriceBar]:
        return self._fx.get(pair, [])


__all__ = ["DataLoader", "PriceDataSource", "FundamentalsDataSource", "IndexMembershipSource", "FXRateSource", "InMemorySource"]

