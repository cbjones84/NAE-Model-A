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
    """require_execution() should raise when execution is off."""
    from nae.core.feature_gates import FeatureGates

    gates = FeatureGates(config_path=None)
    with pytest.raises(PermissionError, match="Execution is disabled"):
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
    finally:
        os.unlink(config_path)


def test_default_mode_is_research_only():
    """Default mode should be research_only."""
    from nae.core.feature_gates import FeatureGates

    gates = FeatureGates(config_path=None)
    assert gates.mode == "research_only"
