import importlib
import sys
from pathlib import Path

import pytest

# Ensure project root is on sys.path for package imports
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

MODULES = [
    "backtester",
    "config",
    "currency_engine",
    "data_loader",
    "email_notifier",
    "execution_engine",
    "fundamental_scoring",
    "models",
    "portfolio_manager",
    "strategy",
    "universe_builder",
]


@pytest.mark.parametrize("module", MODULES)
def test_module_imports(module: str) -> None:
    """Ensure strategy modules can be imported without side effects."""
    importlib.import_module(f"buffett_lynch.{module}")
