"""Facade wiring all modules together for production or research use."""
from __future__ import annotations

from typing import Dict, List

from .backtester import Backtester, BacktestReport
from .config import StrategyConfig
from .currency_engine import CurrencyEngine
from .data_loader import DataLoader
from .execution_engine import ExecutionEngine
from .fundamental_scoring import FundamentalScorer, ScoringRules
from .models import PriceBar, ScoredCompany
from .portfolio_manager import PortfolioManager
from .universe_builder import UniverseBuilder


class BuffettLynchStrategy:
    def __init__(self, loader: DataLoader, scoring_rules: ScoringRules, config: StrategyConfig = StrategyConfig()):
        self.loader = loader
        self.config = config
        self.scorer = FundamentalScorer(scoring_rules)
        self.universe = UniverseBuilder(loader)
        self.portfolio_manager = PortfolioManager(config.portfolio, config.rebalancing)
        self.execution = ExecutionEngine(config.portfolio)
        self.currency = CurrencyEngine(config.backtest.base_currency)

    def backtest(
        self,
        spy_prices: List[PriceBar],
        price_history: Dict[str, List[PriceBar]],
        fundamentals: Dict[str, List[ScoredCompany]],
        fx_history: Dict[str, List[PriceBar]],
    ) -> BacktestReport:
        top100 = self.universe.build_top_market_cap("SP500")
        backtester = Backtester(
            self.universe,
            self.scorer,
            self.portfolio_manager,
            self.execution,
            self.currency,
            self.config.backtest,
        )
        return backtester.run(spy_prices, price_history, fundamentals, top100, fx_history)


__all__ = ["BuffettLynchStrategy"]

