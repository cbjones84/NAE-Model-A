"""Tests that product claims match runtime behaviour."""

from __future__ import annotations

import json

import pytest
from click.testing import CliRunner

from nae.agents.execution_adapter import ExecutionAdapter
from nae.cli.main import cli
from nae.core.feature_gates import get_gates, reset_gates

FULL_EXEC_CONFIG = """
nae:
  mode: full
  execution_enabled: true
broker:
  name: tradier
  api_key: dummy-key-not-real
execution:
  paper_mode: true
  require_confirmation: false
"""

RESEARCH_ONLY_EXEC_FLAG_CONFIG = """
nae:
  mode: research_only
  execution_enabled: true
broker:
  name: tradier
  api_key: dummy-key-not-real
execution:
  paper_mode: true
  require_confirmation: false
"""


@pytest.fixture
def isolated_cwd(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    reset_gates()
    yield tmp_path
    reset_gates()


def test_paper_market_fill_uses_mark_not_zero(isolated_cwd):
    (isolated_cwd / "config.yaml").write_text(FULL_EXEC_CONFIG)
    reset_gates()
    get_gates(config_path=str(isolated_cwd / "config.yaml"))
    adapter = ExecutionAdapter(log_dir=str(isolated_cwd / "logs"))
    adapter._paper_mark_price = lambda symbol: 123.45  # type: ignore[method-assign]

    order = adapter.create_order("SPY", "buy", 1, "market")
    filled = adapter.confirm_and_submit(order)
    assert filled.fill_price == 123.45
    assert filled.fill_price != 0


def test_paper_market_fill_rejects_missing_price(isolated_cwd):
    (isolated_cwd / "config.yaml").write_text(FULL_EXEC_CONFIG)
    reset_gates()
    get_gates(config_path=str(isolated_cwd / "config.yaml"))
    adapter = ExecutionAdapter(log_dir=str(isolated_cwd / "logs"))
    adapter._paper_mark_price = lambda symbol: None  # type: ignore[method-assign]

    order = adapter.create_order("SPY", "buy", 1, "market")
    with pytest.raises(ValueError, match="not filled at"):
        adapter.confirm_and_submit(order)


def test_execute_status_reads_audit_log_across_instances(isolated_cwd):
    logs = isolated_cwd / "logs"
    logs.mkdir()
    entry = {
        "timestamp": "2026-01-01T00:00:00+00:00",
        "event": "paper_order_filled",
        "order_id": "NAE-20260101000000-0001",
        "symbol": "SPY",
        "side": "buy",
        "quantity": 10,
        "status": "filled",
        "fill_price": 450.25,
    }
    (logs / "execution_audit.jsonl").write_text(json.dumps(entry) + "\n", encoding="utf-8")

    later = ExecutionAdapter(log_dir=str(logs))
    hist = later.get_order_history()
    assert len(hist) == 1
    assert hist[0]["order_id"] == "NAE-20260101000000-0001"
    assert hist[0]["status"] == "filled"
    assert hist[0]["fill_price"] == 450.25


def test_cli_execute_status_prints_persisted_order(isolated_cwd):
    logs = isolated_cwd / "logs"
    logs.mkdir()
    entry = {
        "timestamp": "2026-01-01T00:00:00+00:00",
        "event": "paper_order_filled",
        "order_id": "NAE-CLI-1",
        "symbol": "QQQ",
        "side": "sell",
        "quantity": 3,
        "fill_price": 400.0,
    }
    (logs / "execution_audit.jsonl").write_text(json.dumps(entry) + "\n", encoding="utf-8")

    runner = CliRunner()
    result = runner.invoke(cli, ["execute", "status"])
    assert result.exit_code == 0, result.output
    assert "NAE-CLI-1" in result.output
    assert "QQQ" in result.output
    assert "filled" in result.output


def test_cli_execute_blocked_when_research_only_even_if_flag_on(isolated_cwd):
    (isolated_cwd / "config.yaml").write_text(RESEARCH_ONLY_EXEC_FLAG_CONFIG)
    reset_gates()
    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["execute", "order", "--asset", "SPY", "--side", "buy", "--qty", "1"],
    )
    assert result.exit_code == 1
    assert "mode: full" in result.output


def test_cli_backtest_blocked_in_research_only(isolated_cwd):
    (isolated_cwd / "config.yaml").write_text("nae:\n  mode: research_only\n")
    reset_gates()
    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["backtest", "run", "missing.py", "--symbols", "SPY"],
    )
    assert result.exit_code == 1
    assert "research_only" in result.output


def test_cli_regime_requires_pro(isolated_cwd):
    runner = CliRunner()
    result = runner.invoke(cli, ["research", "regime", "--asset", "SPY"])
    assert result.exit_code == 2
    assert "regime_detection_full" in result.output


def test_cli_research_import_csv(isolated_cwd):
    csv_path = isolated_cwd / "spy.csv"
    csv_path.write_text(
        "date,open,high,low,close,volume\n"
        "2024-01-01,100,101,99,100.5,1000\n"
        "2024-01-02,100.5,102,100,101.0,1100\n",
        encoding="utf-8",
    )
    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["research", "import", "--file", str(csv_path), "--symbol", "SPY"],
    )
    assert result.exit_code == 0, result.output
    assert "Rows:" in result.output
    assert "2" in result.output


def test_init_points_to_legal_documents(isolated_cwd):
    runner = CliRunner()
    result = runner.invoke(cli, ["init"], input="I ACCEPT\n")
    assert result.exit_code == 0, result.output
    assert "TERMS_OF_SERVICE.md" in result.output
    assert "RISK_DISCLOSURE.md" in result.output
    assert "does not display the full documents" in result.output
    assert "excerpt" in result.output.lower()
