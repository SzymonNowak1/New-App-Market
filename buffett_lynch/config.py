"""Strategy configuration dataclasses and defaults."""
from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class RebalancingConfig:
    frequency: str = "quarterly"
    min_position: float = 0.02
    max_position: float = 0.25
    max_sector_weight: float = 0.30
    # Added to keep SMA lookback available even if rebalancing config is referenced directly.
    sma_lookback: int = 200


@dataclass
class PortfolioConfig:
    top_n: int = 15
    min_value_score: float = 40.0
    sma_lookback: int = 200
    bear_etfs: Dict[str, str] = field(default_factory=lambda: {"EUR": "ZPR1.DE", "USD": "SHV"})


@dataclass
class BacktestConfig:
    start_date: str = "2000-01-01"
    end_date: str = "2025-12-31"
    base_currency: str = "PLN"
    initial_capital: float = 100000.0
    contributions: Dict[str, float] = field(default_factory=dict)  # date -> amount


@dataclass
class EmailConfig:
    weekly_day: str = "Friday"
    sender: str = "alerts@example.com"
    recipients: List[str] = field(default_factory=list)
    smtp_host: str = "localhost"
    smtp_port: int = 25
    username: Optional[str] = None
    password: Optional[str] = None


@dataclass
class StrategyConfig:
    portfolio: PortfolioConfig = field(default_factory=PortfolioConfig)
    rebalancing: RebalancingConfig = field(default_factory=RebalancingConfig)
    backtest: BacktestConfig = field(default_factory=BacktestConfig)
    email: EmailConfig = field(default_factory=EmailConfig)

