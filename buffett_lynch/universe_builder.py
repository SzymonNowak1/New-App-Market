"""Universe construction for TOP 100 market cap per year."""
from __future__ import annotations

from collections import defaultdict
from typing import Dict, Iterable, List

from .data_loader import DataLoader
from .models import FundamentalSnapshot


class UniverseBuilder:
    def __init__(self, loader: DataLoader):
        self.loader = loader

    def build_top_market_cap(self, index: str) -> Dict[str, List[str]]:
        """Return year->top 100 symbols by market cap using index membership fundamentals."""
        membership = self.loader.load_index_members(index)
        yearly_top: Dict[str, List[str]] = {}
        for year, symbols in membership.items():
            scored = []
            for symbol in symbols:
                fundamentals = [f for f in self.loader.load_fundamentals(symbol) if f.period == year]
                if not fundamentals:
                    continue
                snap = fundamentals[-1]
                scored.append((symbol, snap.market_cap))
            top = [s for s, _ in sorted(scored, key=lambda t: t[1], reverse=True)[:100]]
            yearly_top[year] = top
        return yearly_top


__all__ = ["UniverseBuilder"]

