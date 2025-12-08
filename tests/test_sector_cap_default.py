from buffett_lynch.config import StrategyConfig


def test_sector_cap_default_is_35_percent():
    cfg = StrategyConfig()
    assert cfg.rebalancing.max_sector_weight == 0.35
