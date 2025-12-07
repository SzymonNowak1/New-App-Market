"""Core data structures shared across modules."""
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence


@dataclass
class PriceBar:
    date: str  # YYYY-MM-DD
    close: float


@dataclass
class FundamentalSnapshot:
    period: str  # YYYY
    market_cap: float
    sector: str
    metrics: Dict[str, float]


@dataclass
class ScoredCompany:
    symbol: str
    quality: float
    value: float
    growth: float
    risk: float
    total: float
    sector: str
    market_cap: float
    period: str = ""


@dataclass
class Position:
    symbol: str
    quantity: float
    currency: str
    weight: float
    cost_basis: float
    entry_date: str = ""


@dataclass
class PortfolioState:
    date: str
    cash: Dict[str, float] = field(default_factory=dict)
    positions: Dict[str, Position] = field(default_factory=dict)
    equity_curve_pln: List[float] = field(default_factory=list)
    exposure: Dict[str, float] = field(default_factory=dict)  # bull/bear exposure percentages


@dataclass
class Order:
    symbol: str
    action: str  # BUY or SELL
    quantity: float
    currency: str
    reason: str
    price: Optional[float] = None


@dataclass
class ExecutionResult:
    orders: List[Order]
    portfolio_value_pln: float


@dataclass
class EmailPayload:
    subject: str
    body: str
    attachments: Optional[Sequence[str]] = None

