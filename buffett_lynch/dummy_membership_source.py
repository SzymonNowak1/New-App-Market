# buffett_lynch/dummy_membership_source.py

from __future__ import annotations
from typing import Dict, List

from .data_loader import IndexMembershipSource
from .models import FundamentalSnapshot


class DummyIndexMembershipSource(IndexMembershipSource):
    """
    Minimalne źródło składów indeksu, używane tylko do DEBUG.

    Bierze wszystkie symbole dostępne w fundamentals_source
    i zakłada, że należą do indeksu dla wszystkich lat.
    """

    def __init__(self, fundamentals_source):
        self.fundamentals_source = fundamentals_source

    def members(self, index: str) -> Dict[str, List[str]]:
        """Zwraca mapping: rok -> lista symboli."""
        all_fundamentals = self.fundamentals_source.all_fundamentals()
        symbols = list(all_fundamentals.keys())

        # Ustalmy lata dostępnych raportów
        years = set()
        for snaps in all_fundamentals.values():
            for snap in snaps:
                years.add(snap.period)

        years = sorted(list(years))

        return {year: symbols for year in years}
