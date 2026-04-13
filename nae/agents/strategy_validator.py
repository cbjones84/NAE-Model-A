"""
NAE Strategy Validator (derived from Donnie architecture)

Validates user-defined strategy syntax and structure.
Orchestrates backtests against the unified backtesting engine.
Does NOT auto-route strategies to execution or score them for "profitability."

The user decides which strategies to test and whether to act on results.
"""

import os
import json
import datetime
import logging
import importlib.util
from typing import Dict, Any, List, Optional
from pathlib import Path

logger = logging.getLogger("nae.validator")


REQUIRED_STRATEGY_HOOKS = ["should_enter", "should_exit"]
OPTIONAL_STRATEGY_HOOKS = ["position_size", "on_data", "on_bar", "filter"]


class StrategyValidationError(Exception):
    """Raised when a strategy file fails validation."""
    pass


class StrategyValidator:
    """
    Validates user-authored strategy files and coordinates backtests.

    Responsibilities:
    - Check that strategy Python files have required hooks
    - Validate strategy parameters are within sane bounds
    - Run backtests via the backtesting engine and return raw results
    - Store strategy metadata for user reference

    This validator does NOT:
    - Rank strategies by profitability
    - Recommend which strategy to use
    - Auto-deploy strategies to execution
    - Modify user strategies
    """

    def __init__(self, strategies_dir: str = "./strategies"):
        self.strategies_dir = Path(strategies_dir)
        self.strategies_dir.mkdir(parents=True, exist_ok=True)
        self._registry: Dict[str, Dict[str, Any]] = {}

    def create_strategy_scaffold(self, name: str) -> str:
        """
        Create a new strategy file from the template.

        Returns the path to the created file.
        """
        safe_name = name.replace(" ", "_").replace("-", "_").lower()
        filepath = self.strategies_dir / f"{safe_name}.py"

        if filepath.exists():
            raise FileExistsError(f"Strategy '{safe_name}' already exists at {filepath}")

        template = f'''"""
User-Defined Strategy: {name}

IMPORTANT: This is YOUR strategy. NAE does not endorse, recommend,
or guarantee the performance of any strategy. You are solely
responsible for all trading decisions.

Required hooks:
  should_enter(data) -> bool   : Return True when YOUR entry conditions are met
  should_exit(data) -> bool    : Return True when YOUR exit conditions are met

Optional hooks:
  position_size(data, capital) -> int : Return number of shares/contracts
  on_data(data) -> None               : Called on each data bar
  filter(symbol) -> bool               : Return True if symbol passes YOUR filter
"""


# Your strategy parameters — configure these yourself
PARAMS = {{
    "lookback_period": 20,
    "threshold": 0.0,
}}


def should_enter(data: dict) -> bool:
    """
    Define YOUR entry conditions here.

    Args:
        data: dict with keys 'open', 'high', 'low', 'close', 'volume',
              'sma_20', 'sma_50', 'rsi_14', and any custom indicators

    Returns:
        True if YOUR conditions for entering a position are met
    """
    # TODO: Implement your entry logic
    return False


def should_exit(data: dict) -> bool:
    """
    Define YOUR exit conditions here.

    Args:
        data: same as should_enter

    Returns:
        True if YOUR conditions for exiting a position are met
    """
    # TODO: Implement your exit logic
    return False


def position_size(data: dict, capital: float) -> int:
    """
    Define YOUR position sizing logic here.

    Args:
        data: market data dict
        capital: available capital

    Returns:
        Number of shares/contracts to trade
    """
    return 1
'''

        with open(filepath, "w") as f:
            f.write(template)

        logger.info(f"Created strategy scaffold: {filepath}")
        return str(filepath)

    def validate_strategy(self, filepath: str) -> Dict[str, Any]:
        """
        Validate a strategy file has required hooks and valid structure.

        Returns validation result dict.
        """
        path = Path(filepath)
        if not path.exists():
            raise StrategyValidationError(f"Strategy file not found: {filepath}")

        if not path.suffix == ".py":
            raise StrategyValidationError("Strategy files must be Python (.py)")

        # Load module
        try:
            spec = importlib.util.spec_from_file_location("user_strategy", str(path))
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
        except Exception as e:
            raise StrategyValidationError(f"Failed to load strategy: {e}")

        result = {
            "file": str(path),
            "valid": True,
            "hooks_found": [],
            "hooks_missing": [],
            "warnings": [],
            "validated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }

        # Check required hooks
        for hook in REQUIRED_STRATEGY_HOOKS:
            if hasattr(module, hook) and callable(getattr(module, hook)):
                result["hooks_found"].append(hook)
            else:
                result["hooks_missing"].append(hook)
                result["valid"] = False

        # Check optional hooks
        for hook in OPTIONAL_STRATEGY_HOOKS:
            if hasattr(module, hook) and callable(getattr(module, hook)):
                result["hooks_found"].append(hook)

        # Check for PARAMS
        if hasattr(module, "PARAMS") and isinstance(module.PARAMS, dict):
            result["parameters"] = module.PARAMS
        else:
            result["warnings"].append("No PARAMS dict found — strategy has no configurable parameters")

        # Warn if hooks return hardcoded values
        import inspect
        for hook in ["should_enter", "should_exit"]:
            if hasattr(module, hook):
                source = inspect.getsource(getattr(module, hook))
                if source.strip().endswith("return False") or source.strip().endswith("return True"):
                    result["warnings"].append(
                        f"'{hook}' appears to return a hardcoded value — "
                        f"implement your own logic"
                    )

        # Register
        name = path.stem
        self._registry[name] = result

        logger.info(f"Validated strategy '{name}': valid={result['valid']}")
        return result

    def list_strategies(self) -> List[Dict[str, Any]]:
        """List all strategy files in the strategies directory."""
        strategies = []
        for f in sorted(self.strategies_dir.glob("*.py")):
            if f.name.startswith("__"):
                continue
            info = {
                "name": f.stem,
                "file": str(f),
                "size_bytes": f.stat().st_size,
                "modified": datetime.datetime.fromtimestamp(
                    f.stat().st_mtime
                ).isoformat(),
            }
            if f.stem in self._registry:
                info["validation"] = self._registry[f.stem]
            strategies.append(info)
        return strategies

    def run_backtest(
        self,
        strategy_path: str,
        symbols: List[str],
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        initial_capital: float = 100_000.0,
    ) -> Dict[str, Any]:
        """
        Run a backtest for a user-defined strategy.

        Returns raw backtest results — the user interprets them.
        """
        # Validate first
        validation = self.validate_strategy(strategy_path)
        if not validation["valid"]:
            raise StrategyValidationError(
                f"Strategy failed validation: {validation['hooks_missing']}"
            )

        # Load the strategy module
        spec = importlib.util.spec_from_file_location("user_strategy", strategy_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        strategy_dict = {
            "name": Path(strategy_path).stem,
            "entry_fn": module.should_enter,
            "exit_fn": module.should_exit,
            "size_fn": getattr(module, "position_size", lambda d, c: 1),
            "params": getattr(module, "PARAMS", {}),
        }

        # Try unified backtester, fall back to simple engine
        try:
            from nae.tools.backtesting.engine import SimpleBacktestEngine
            engine = SimpleBacktestEngine()
            result = engine.run(
                strategy=strategy_dict,
                symbols=symbols,
                start_date=start_date,
                end_date=end_date,
                initial_capital=initial_capital,
            )
            return result
        except Exception as e:
            logger.error(f"Backtest failed: {e}")
            raise
