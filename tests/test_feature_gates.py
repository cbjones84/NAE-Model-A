"""Tests for the feature gate system."""

import os
import tempfile
import pytest
from pathlib import Path


def test_default_gates_block_execution():
    """Execution must be disabled by default."""
    from nae.core.feature_gates import FeatureGates

    gates = FeatureGates(config_path=None)
    assert gates.execution_allowed is False
    assert gates.paper_mode is True
    assert gates.confirmation_required is True


def test_require_execution_raises_when_disabled():
    """require_execution() should raise when mode is not full (default)."""
    from nae.core.feature_gates import FeatureGates

    gates = FeatureGates(config_path=None)
    with pytest.raises(PermissionError, match="mode: full"):
        gates.require_execution()


def test_config_loading():
    """Config file should override defaults."""
    from nae.core.feature_gates import FeatureGates

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".yaml", delete=False
    ) as f:
        f.write(
            "nae:\n"
            "  mode: backtest\n"
            "  execution_enabled: true\n"
            "broker:\n"
            "  name: tradier\n"
            "  api_key: test_key_12345\n"
        )
        f.flush()
        config_path = f.name

    try:
        gates = FeatureGates(config_path=config_path)
        assert gates.mode == "backtest"
        assert gates.execution_allowed is True
        assert gates.broker_configured is True
        assert gates.backtest_allowed is True
        with pytest.raises(PermissionError, match="mode: full"):
            gates.require_execution()
    finally:
        os.unlink(config_path)


def test_research_only_blocks_execute_even_when_flag_on():
    """research_only must refuse orders even if execution_enabled is true."""
    from nae.core.feature_gates import FeatureGates

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".yaml", delete=False
    ) as f:
        f.write(
            "nae:\n"
            "  mode: research_only\n"
            "  execution_enabled: true\n"
            "broker:\n"
            "  name: tradier\n"
            "  api_key: test_key_12345\n"
        )
        f.flush()
        config_path = f.name

    try:
        gates = FeatureGates(config_path=config_path)
        assert gates.execution_allowed is True
        assert gates.backtest_allowed is False
        with pytest.raises(PermissionError, match="research_only"):
            gates.require_backtest()
        with pytest.raises(PermissionError, match="mode: full"):
            gates.require_execution()
    finally:
        os.unlink(config_path)


def test_full_mode_allows_execution_when_enabled():
    from nae.core.feature_gates import FeatureGates

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".yaml", delete=False
    ) as f:
        f.write(
            "nae:\n"
            "  mode: full\n"
            "  execution_enabled: true\n"
            "broker:\n"
            "  name: alpaca\n"
            "  api_key: test_key_12345\n"
        )
        f.flush()
        config_path = f.name

    try:
        gates = FeatureGates(config_path=config_path)
        gates.require_backtest()
        gates.require_execution()
    finally:
        os.unlink(config_path)


def test_unknown_mode_fails_closed_to_research_only():
    from nae.core.feature_gates import FeatureGates

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".yaml", delete=False
    ) as f:
        f.write("nae:\n  mode: experimental\n")
        f.flush()
        config_path = f.name

    try:
        gates = FeatureGates(config_path=config_path)
        assert gates.mode == "research_only"
        assert gates.backtest_allowed is False
    finally:
        os.unlink(config_path)


def test_default_mode_is_research_only():
    """Default mode should be research_only."""
    from nae.core.feature_gates import FeatureGates

    gates = FeatureGates(config_path=None)
    assert gates.mode == "research_only"
