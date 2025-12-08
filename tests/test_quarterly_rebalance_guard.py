"""Ensure orders are only produced on quarterly rebalancing dates."""

from buffett_lynch.config import PortfolioConfig
from buffett_lynch.execution_engine import ExecutionEngine
from buffett_lynch.models import ScoredCompany


def _make_pick(symbol: str, total: float = 1.0) -> ScoredCompany:
    return ScoredCompany(
        symbol=symbol,
        quality=80.0,
        value=50.0,
        growth=60.0,
        moat=55.0,
        risk=10.0,
        total=total,
        sector="Tech",
        market_cap=1_000_000_000,
    )


def test_orders_blocked_when_not_rebalance_date():
    engine = ExecutionEngine(PortfolioConfig())
    picks = [_make_pick("AAA")]
    price_map = {"AAA": 100.0}
    sma_map = {"AAA": {"2020-01-10": 90.0}}

    orders = engine.generate_orders(
        date="2020-01-10",
        picks=picks,
        top100=["AAA"],
        spy_regime="bull",
        price_map=price_map,
        sma_map=sma_map,
        portfolio={},
        rebalance_due=False,
    )

    assert orders == []


def test_rebalance_schedule_picks_quarter_end_dates():
    # Build a Backtester instance without running its full initializer.
    from buffett_lynch.backtester import Backtester
    from buffett_lynch.config import RebalancingConfig

    bt = Backtester.__new__(Backtester)
    bt.portfolio_manager = type("PM", (), {"rebalance_cfg": RebalancingConfig(frequency="quarterly")})()

    dates = [
        "2020-01-02",
        "2020-03-30",
        "2020-03-31",
        "2020-04-01",
        "2020-06-29",
        "2020-06-30",
        "2020-12-15",
    ]

    schedule = bt._rebalance_schedule(dates)

    assert schedule == ["2020-03-31", "2020-06-30", "2020-12-15"]

