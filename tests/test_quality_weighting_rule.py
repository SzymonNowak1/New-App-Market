import pytest

from buffett_lynch.config import PortfolioConfig, RebalancingConfig
from buffett_lynch.models import ScoredCompany
from buffett_lynch.portfolio_manager import PortfolioManager


def _sample_company(symbol: str, quality: float, sector: str = "Tech") -> ScoredCompany:
    return ScoredCompany(
        symbol=symbol,
        quality=quality,
        value=50.0,
        growth=50.0,
        moat=50.0,
        risk=10.0,
        total=0.0,
        sector=sector,
        market_cap=1e9,
    )


def test_quality_weighting_remains_proportional():
    portfolio_cfg = PortfolioConfig(top_n=3)
    rebalance_cfg = RebalancingConfig(
        min_position=0.0,
        max_position=1.0,
        max_sector_weight=1.0,
    )
    pm = PortfolioManager(portfolio_cfg, rebalance_cfg)

    picks = [
        _sample_company("A", quality=2.0),
        _sample_company("B", quality=1.0),
        _sample_company("C", quality=1.0),
    ]

    allocations = pm.build_weights(picks)
    weight_map = {a.symbol: a.weight for a in allocations}
    quality_sum = sum(p.quality for p in picks)

    assert pytest.approx(sum(weight_map.values()), rel=1e-6) == 1.0
    for company in picks:
        expected_weight = company.quality / quality_sum
        assert pytest.approx(weight_map[company.symbol], rel=1e-6) == expected_weight
