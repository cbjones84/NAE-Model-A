"""
Smoke tests for the simple backtest engine.

These tests drive the engine with a hand-built synthetic price series so
they do NOT require yfinance or network access, and they exercise the
metrics path (Sharpe/Sortino/max drawdown) that previously had no
automated coverage.
"""

from __future__ import annotations

from typing import Any, Dict, List

import pytest

from nae.tools.backtesting.engine import SimpleBacktestEngine


def _synthetic_bars(n: int = 60, start: float = 100.0, step: float = 1.0) -> List[Dict[str, Any]]:
    """Build a simple monotonically-rising price series."""
    bars = []
    price = start
    for i in range(n):
        price += step
        bars.append(
            {
                "timestamp": f"2025-01-{(i % 28) + 1:02d}",
                "open": price - 0.5,
                "high": price + 0.5,
                "low": price - 1.0,
                "close": price,
                "volume": 1_000 + i,
            }
        )
    return bars


class _StubEngine(SimpleBacktestEngine):
    """Injects synthetic data so tests do not need yfinance."""

    def __init__(self, bars: List[Dict[str, Any]]):
        self._bars = bars

    def _fetch_data(self, symbol, start_date, end_date):  # type: ignore[override]
        return list(self._bars)


def test_engine_produces_valid_result_shape():
    bars = _synthetic_bars(80)
    engine = _StubEngine(bars)

    strategy = {
        "name": "always_in",
        "entry_fn": lambda bar: True,
        "exit_fn": lambda bar: False,
        "size_fn": lambda bar, cap: 1,
    }
    result = engine.run(strategy=strategy, symbols=["TEST"], initial_capital=10_000.0)

    for field in (
        "strategy_name",
        "symbols",
        "total_return_pct",
        "sharpe_ratio",
        "sortino_ratio",
        "max_drawdown_pct",
        "data_points_used",
        "disclaimer",
    ):
        assert field in result, f"missing field: {field}"

    assert result["strategy_name"] == "always_in"
    assert result["data_points_used"] == len(bars)
    # A disclaimer must always travel with results for compliance.
    assert "not indicative" in result["disclaimer"].lower()


def test_sortino_does_not_explode_when_no_losing_days():
    # Monotonically rising price → no downside returns. Previously the
    # engine substituted 0.0001 for the downside stdev, producing an
    # absurdly inflated Sortino. After the fix it must report 0.0.
    bars = _synthetic_bars(80, step=1.0)
    engine = _StubEngine(bars)

    strategy = {
        "name": "buy_and_hold",
        "entry_fn": lambda bar: True,
        "exit_fn": lambda bar: False,
    }
    result = engine.run(strategy=strategy, symbols=["TEST"], initial_capital=10_000.0)

    assert result["sortino_ratio"] == pytest.approx(0.0)


def test_engine_handles_empty_data_gracefully():
    engine = _StubEngine([])
    strategy = {
        "name": "noop",
        "entry_fn": lambda bar: False,
        "exit_fn": lambda bar: False,
    }
    result = engine.run(strategy=strategy, symbols=["TEST"], initial_capital=5_000.0)

    assert result["total_trades"] == 0
    assert result["data_points_used"] == 0
    assert result["final_capital"] == pytest.approx(5_000.0)
