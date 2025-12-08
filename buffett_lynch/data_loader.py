"""Data access layer for prices, fundamentals, index membership, and FX."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Protocol

from .fundamental_metrics import FundamentalMetrics
from .fundamental_raw_metrics import FundamentalRawMetrics
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
    _enriched_fundamentals: Optional[Dict[str, List[FundamentalSnapshot]]] = field(
        default=None, init=False, repr=False
    )

    def load_price_history(self, symbol: str) -> List[PriceBar]:
        return sorted(self.price_source.price_history(symbol), key=lambda b: b.date)

    def load_fundamentals(self, symbol: str) -> List[FundamentalSnapshot]:
        if self._enriched_fundamentals is None:
            all_fundamentals = None
            if hasattr(self.fundamentals_source, "all_fundamentals"):
                all_fundamentals = self.fundamentals_source.all_fundamentals()

            if all_fundamentals is not None:
                raw_enriched = FundamentalRawMetrics().enrich_moat_raw_metrics(all_fundamentals)
                self._enriched_fundamentals = FundamentalMetrics().enrich_moat_percentiles(
                    raw_enriched
                )

        if self._enriched_fundamentals is not None:
            snaps = self._enriched_fundamentals.get(symbol, [])
            if snaps:
                return sorted(snaps, key=lambda f: f.period)

        raw = self.fundamentals_source.fundamentals(symbol)
        raw_enriched = FundamentalRawMetrics().enrich_moat_raw_metrics({symbol: raw})
        enriched_single = FundamentalMetrics().enrich_moat_percentiles({symbol: raw_enriched.get(symbol, raw)})
        snaps = enriched_single.get(symbol, raw)
        return sorted(snaps, key=lambda f: f.period)

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

    def all_fundamentals(self) -> Dict[str, List[FundamentalSnapshot]]:
        return self._fundamentals

    def members(self, index: str) -> Dict[str, List[str]]:
        return self._membership.get(index, {})

    def history(self, pair: str) -> List[PriceBar]:
        return self._fx.get(pair, [])


__all__ = ["DataLoader", "PriceDataSource", "FundamentalsDataSource", "IndexMembershipSource", "FXRateSource", "InMemorySource"]

