"""
NAE CLI — Command-Line Interface

Primary user interface for NAE Platform (Model A).
All commands are user-initiated. NAE does not make decisions.

Usage:
    python -m nae <command> [options]
    nae <command> [options]        (if installed via pip)
"""

import click
import json
import sys
import os
import logging
from pathlib import Path

from nae import __version__, __product__, __tagline__


def _setup_logging(level: str = "INFO") -> None:
    log_dir = Path("./logs")
    log_dir.mkdir(exist_ok=True)
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        handlers=[
            logging.FileHandler(log_dir / "nae.log"),
            logging.StreamHandler(),
        ],
    )


@click.group()
@click.version_option(version=__version__, prog_name=__product__)
def cli():
    """NAE Platform — AI-Assisted Trading Research Infrastructure

    Your AI. Your Control. Your Privacy.

    NAE is a research and analysis tool. It does NOT provide
    financial advice or trade recommendations.
    """
    pass


# ── INIT ────────────────────────────────────────────────────────

@cli.command()
@click.option("--dir", "target_dir", default=".", help="Directory to initialize")
def init(target_dir: str):
    """Initialize a new NAE workspace with config and directories."""
    from nae.core.disclaimer import FIRST_RUN_NOTICE

    click.echo(FIRST_RUN_NOTICE)
    click.echo("")
    accepted = click.prompt(
        "  Do you accept these terms? Type 'I ACCEPT' to continue",
        type=str,
    )

    if accepted.strip().upper() != "I ACCEPT":
        click.echo("\n  You must accept the terms to use NAE. Exiting.")
        sys.exit(1)

    target = Path(target_dir)

    # Create directories
    for d in ["logs", "data", "reports", "strategies"]:
        (target / d).mkdir(parents=True, exist_ok=True)

    # Create config from template
    config_path = target / "config.yaml"
    if not config_path.exists():
        config_template = """# NAE Platform Configuration
# ─────────────────────────────────────────────────────────
# All settings are user-controlled. NAE does not modify
# this file automatically.
# ─────────────────────────────────────────────────────────

nae:
  mode: research_only          # research_only | backtest | full
  execution_enabled: false     # Must be explicitly set to true

broker:
  name: null                   # tradier | alpaca
  api_key: null                # Your API key
  api_secret: null             # Your API secret (Alpaca only)
  sandbox: true                # true = paper trading (default)

research:
  data_sources:
    - yahoo_finance
  assets: []                   # Your watchlist — add symbols here

backtesting:
  default_period_days: 365
  output_format: csv           # csv | json
  output_directory: ./reports

execution:
  require_confirmation: true   # Prompt before every order
  max_order_size_usd: 1000.0   # Safety limit — adjust to your risk tolerance
  paper_mode: true             # true = simulated orders (no real money)

logging:
  level: INFO
  directory: ./logs
"""
        config_path.write_text(config_template)
        click.echo(f"  ✓ Created config.yaml")

    # Log acceptance
    acceptance_log = target / "logs" / "acceptance.log"
    import datetime
    with open(acceptance_log, "a") as f:
        f.write(
            f"{datetime.datetime.now(datetime.timezone.utc).isoformat()} "
            f"Terms accepted by user\n"
        )

    click.echo(f"  ✓ Created workspace directories")
    click.echo(f"  ✓ Logged acceptance")
    click.echo("")
    click.echo("  NAE workspace initialized. Next steps:")
    click.echo("    1. Edit config.yaml with your settings")
    click.echo("    2. Run 'nae status' to verify setup")
    click.echo("    3. Run 'nae research scan --asset SPY' to generate research")
    click.echo("    4. Run 'nae strategy create my_strategy' to start building")


# ── STATUS ──────────────────────────────────────────────────────

@cli.command()
def status():
    """Show system status, health, and configuration."""
    _setup_logging("WARNING")
    from nae.agents.system_monitor import SystemMonitor
    from nae.core.feature_gates import get_gates

    gates = get_gates()
    monitor = SystemMonitor()

    click.echo(f"\n  {__product__} v{__version__}")
    click.echo(f"  {__tagline__}")
    click.echo(f"  {'─' * 50}")

    # Mode
    click.echo(f"  Mode:       {gates.mode}")
    click.echo(f"  Execution:  {'enabled' if gates.execution_allowed else 'disabled'}")
    click.echo(f"  Paper mode: {'yes' if gates.paper_mode else 'no (LIVE)'}")

    # Broker
    broker = gates.get("broker.name", "not configured")
    click.echo(f"  Broker:     {broker}")
    if gates.broker_configured:
        click.echo(f"  Sandbox:    {gates.get('broker.sandbox', True)}")

    # System
    status_data = monitor.system_status()
    if "cpu_percent" in status_data:
        click.echo(f"\n  System Resources:")
        click.echo(f"    CPU:    {status_data['cpu_percent']}%")
        click.echo(f"    Memory: {status_data['memory_used_mb']}MB / {status_data['memory_total_mb']}MB")
        click.echo(f"    Disk:   {status_data['disk_used_gb']}GB / {status_data['disk_total_gb']}GB")

    click.echo(f"\n  Data files: {status_data.get('data_files', 0)}")
    click.echo(f"  Log files:  {status_data.get('log_files', 0)}")
    click.echo("")


# ── RESEARCH ────────────────────────────────────────────────────

@cli.group()
def research():
    """AI-assisted market research and analysis.

    All output is raw research data — not trade recommendations.
    """
    pass


@research.command("scan")
@click.option("--asset", required=True, help="Ticker symbol (e.g. SPY, BTC-USD)")
@click.option("--period", default="1y", help="Data period (1mo, 3mo, 6mo, 1y, 2y)")
@click.option("--format", "fmt", default="json", help="Output format (json, csv)")
def research_scan(asset: str, period: str, fmt: str):
    """Generate a research report for a symbol."""
    _setup_logging()
    from nae.agents.research_engine import ResearchEngine
    from nae.core.disclaimer import SHORT_DISCLAIMER

    engine = ResearchEngine()
    click.echo(f"\n  Scanning {asset} ({period})...")

    try:
        report = engine.generate_report(asset, period=period, export_format=fmt)
        click.echo(f"\n  Symbol:      {report.symbol}")
        click.echo(f"  Data points: {report.data_points}")
        click.echo(f"  Period:      {report.period_days} trading days")
        click.echo(f"\n  Metrics:")
        for k, v in report.metrics.items():
            if isinstance(v, float):
                click.echo(f"    {k:30s} {v:>12.4f}")
            else:
                click.echo(f"    {k:30s} {v}")
        click.echo(f"\n  Patterns:")
        for p in report.patterns:
            click.echo(f"    • {p}")
        click.echo(f"\n  ⚠ {SHORT_DISCLAIMER}")
    except Exception as e:
        click.echo(f"  Error: {e}", err=True)
        sys.exit(1)


@research.command("patterns")
@click.option("--asset", required=True, help="Ticker symbol")
@click.option("--period", default="1y", help="Data period")
def research_patterns(asset: str, period: str):
    """Detect technical patterns in price data."""
    _setup_logging()
    from nae.agents.research_engine import ResearchEngine
    from nae.core.disclaimer import SHORT_DISCLAIMER

    engine = ResearchEngine()
    click.echo(f"\n  Analyzing patterns for {asset}...")

    data = engine.fetch_market_data(asset, period=period)
    patterns = engine.detect_patterns(data)

    click.echo(f"\n  Patterns detected ({len(patterns)}):")
    for p in patterns:
        click.echo(f"    • {p}")
    click.echo(f"\n  ⚠ {SHORT_DISCLAIMER}")


@research.command("correlations")
@click.option("--assets", required=True, help="Comma-separated symbols (e.g. SPY,QQQ,BTC-USD)")
@click.option("--period", default="1y", help="Data period")
def research_correlations(assets: str, period: str):
    """Compute pairwise correlation matrix for multiple symbols."""
    _setup_logging()
    from nae.agents.research_engine import ResearchEngine
    from nae.core.disclaimer import SHORT_DISCLAIMER

    symbols = [s.strip().upper() for s in assets.split(",")]
    engine = ResearchEngine()

    click.echo(f"\n  Computing correlations for {', '.join(symbols)}...")
    matrix = engine.correlation_matrix(symbols, period=period)

    # Display matrix
    header = f"  {'':>10}" + "".join(f"{s:>10}" for s in symbols)
    click.echo(f"\n{header}")
    for s1 in symbols:
        row = f"  {s1:>10}"
        for s2 in symbols:
            val = matrix.get(s1, {}).get(s2, 0)
            row += f"{val:>10.4f}"
        click.echo(row)
    click.echo(f"\n  ⚠ {SHORT_DISCLAIMER}")


@research.command("regime")
@click.option("--asset", required=True, help="Ticker symbol")
@click.option("--period", default="1y", help="Data period")
def research_regime(asset: str, period: str):
    """Detect the current market regime for a symbol."""
    _setup_logging()
    from nae.agents.research_engine import ResearchEngine
    from nae.tools.analysis.regime_detection import RegimeDetector
    from nae.core.disclaimer import SHORT_DISCLAIMER

    engine = ResearchEngine()
    detector = RegimeDetector()

    click.echo(f"\n  Detecting regime for {asset}...")
    data = engine.fetch_market_data(asset, period=period)
    closes = [p.close_price for p in data]
    analysis = detector.detect(closes, symbol=asset)

    click.echo(f"\n  Symbol:     {analysis.symbol}")
    click.echo(f"  Regime:     {analysis.regime.value}")
    click.echo(f"  Confidence: {analysis.confidence:.0%}")
    click.echo(f"\n  Features:")
    for k, v in analysis.features.items():
        click.echo(f"    {k:30s} {v}")
    click.echo(f"\n  ⚠ {analysis.note}")
    click.echo(f"  ⚠ {SHORT_DISCLAIMER}")


# ── STRATEGY ────────────────────────────────────────────────────

@cli.group()
def strategy():
    """Create, validate, and manage user-defined strategies.

    Strategies are authored by the user. NAE provides the framework.
    """
    pass


@strategy.command("create")
@click.argument("name")
@click.option("--dir", "strategies_dir", default="./strategies", help="Strategies directory")
def strategy_create(name: str, strategies_dir: str):
    """Create a new strategy file from template."""
    from nae.agents.strategy_validator import StrategyValidator

    validator = StrategyValidator(strategies_dir=strategies_dir)
    try:
        path = validator.create_strategy_scaffold(name)
        click.echo(f"\n  ✓ Created strategy: {path}")
        click.echo(f"  Edit the file to implement your entry/exit logic.")
        click.echo(f"  Then validate with: nae strategy validate {path}")
    except FileExistsError as e:
        click.echo(f"  Error: {e}", err=True)
        sys.exit(1)


@strategy.command("validate")
@click.argument("filepath")
def strategy_validate(filepath: str):
    """Validate a strategy file for required hooks."""
    from nae.agents.strategy_validator import StrategyValidator

    validator = StrategyValidator()
    try:
        result = validator.validate_strategy(filepath)
        if result["valid"]:
            click.echo(f"\n  ✓ Strategy is valid")
        else:
            click.echo(f"\n  ✗ Strategy is invalid")
            click.echo(f"    Missing hooks: {result['hooks_missing']}")

        click.echo(f"    Hooks found: {result['hooks_found']}")
        for w in result.get("warnings", []):
            click.echo(f"    ⚠ {w}")
    except Exception as e:
        click.echo(f"  Error: {e}", err=True)
        sys.exit(1)


@strategy.command("list")
@click.option("--dir", "strategies_dir", default="./strategies", help="Strategies directory")
def strategy_list(strategies_dir: str):
    """List all strategy files in the workspace."""
    from nae.agents.strategy_validator import StrategyValidator

    validator = StrategyValidator(strategies_dir=strategies_dir)
    strategies = validator.list_strategies()

    if not strategies:
        click.echo("\n  No strategies found. Create one with: nae strategy create <name>")
        return

    click.echo(f"\n  Strategies ({len(strategies)}):")
    for s in strategies:
        click.echo(f"    • {s['name']:20s}  {s['modified'][:10]}  {s['size_bytes']:>6} bytes")


# ── BACKTEST ────────────────────────────────────────────────────

@cli.group()
def backtest():
    """Run backtests on user-defined strategies.

    Results are historical simulations — not predictions.
    Past performance does not indicate future results.
    """
    pass


@backtest.command("run")
@click.argument("strategy_path")
@click.option("--symbols", required=True, help="Comma-separated symbols (e.g. SPY,AAPL)")
@click.option("--start", "start_date", default=None, help="Start date (YYYY-MM-DD)")
@click.option("--end", "end_date", default=None, help="End date (YYYY-MM-DD)")
@click.option("--capital", default=100000.0, help="Initial capital")
@click.option("--export", "export_path", default=None, help="Export results to JSON file")
def backtest_run(strategy_path: str, symbols: str, start_date, end_date, capital, export_path):
    """Run a backtest for a user-defined strategy."""
    _setup_logging()
    from nae.agents.strategy_validator import StrategyValidator
    from nae.tools.backtesting.engine import BacktestResult
    from nae.core.disclaimer import REPORT_DISCLAIMER

    symbol_list = [s.strip().upper() for s in symbols.split(",")]
    validator = StrategyValidator()

    click.echo(f"\n  Running backtest: {strategy_path}")
    click.echo(f"  Symbols: {', '.join(symbol_list)}")
    click.echo(f"  Capital: ${capital:,.2f}")

    try:
        result = validator.run_backtest(
            strategy_path=strategy_path,
            symbols=symbol_list,
            start_date=start_date,
            end_date=end_date,
            initial_capital=capital,
        )

        # Display results
        click.echo(f"\n  {'─' * 50}")
        click.echo(f"  BACKTEST RESULTS")
        click.echo(f"  {'─' * 50}")
        click.echo(f"  Strategy:       {result['strategy_name']}")
        click.echo(f"  Period:         {result['start_date']} → {result['end_date']}")
        click.echo(f"  Data points:    {result['data_points_used']}")
        click.echo(f"")
        click.echo(f"  Initial:        ${result['initial_capital']:>12,.2f}")
        click.echo(f"  Final:          ${result['final_capital']:>12,.2f}")
        click.echo(f"  Return:         {result['total_return_pct']:>11.2f}%")
        click.echo(f"")
        click.echo(f"  Trades:         {result['total_trades']}")
        click.echo(f"  Win rate:       {result['win_rate_pct']:>11.2f}%")
        click.echo(f"  Avg return:     {result['avg_trade_return_pct']:>11.2f}%")
        click.echo(f"")
        click.echo(f"  Max drawdown:   {result['max_drawdown_pct']:>11.2f}%")
        click.echo(f"  Sharpe:         {result['sharpe_ratio']:>11.4f}")
        click.echo(f"  Sortino:        {result['sortino_ratio']:>11.4f}")
        click.echo(f"  Volatility:     {result['volatility_annual_pct']:>11.2f}%")
        click.echo(f"\n{REPORT_DISCLAIMER}")

        if export_path:
            Path(export_path).parent.mkdir(parents=True, exist_ok=True)
            with open(export_path, "w") as f:
                json.dump(result, f, indent=2)
            click.echo(f"\n  Exported to: {export_path}")

    except Exception as e:
        click.echo(f"  Error: {e}", err=True)
        sys.exit(1)


# ── EXECUTE ─────────────────────────────────────────────────────

@cli.group()
def execute():
    """User-controlled order execution.

    Execution is DISABLED by default. You must explicitly enable it
    in config.yaml. All orders require your confirmation.
    """
    pass


@execute.command("enable")
def execute_enable():
    """Show instructions for enabling execution."""
    click.echo("""
  ⚠ Execution is disabled by default for your protection.

  To enable, edit config.yaml and set:

    nae:
      execution_enabled: true

    execution:
      paper_mode: true            # Start with paper trading
      require_confirmation: true  # Keep confirmations on

  You are solely responsible for all trades executed through NAE.
  NAE does not provide financial advice or trade recommendations.
""")


@execute.command("order")
@click.option("--asset", required=True, help="Ticker symbol")
@click.option("--side", required=True, type=click.Choice(["buy", "sell"]))
@click.option("--qty", required=True, type=int, help="Quantity")
@click.option("--type", "order_type", default="market", type=click.Choice(["market", "limit", "stop"]))
@click.option("--price", default=None, type=float, help="Limit price")
def execute_order(asset: str, side: str, qty: int, order_type: str, price: float):
    """Submit a user-initiated order to the configured broker."""
    _setup_logging()
    from nae.agents.execution_adapter import ExecutionAdapter

    adapter = ExecutionAdapter()

    try:
        order = adapter.create_order(
            symbol=asset,
            side=side,
            quantity=qty,
            order_type=order_type,
            price=price,
        )
        click.echo(f"\n  Order created: {order.order_id}")
        click.echo(f"  {order.side.value.upper()} {order.quantity} {order.symbol} @ {order.order_type.value}")
        if order.price:
            click.echo(f"  Price: ${order.price:,.2f}")

        result = adapter.confirm_and_submit(order)
        click.echo(f"\n  Status: {result.status.value}")
        if result.broker_order_id:
            click.echo(f"  Broker ID: {result.broker_order_id}")

    except PermissionError as e:
        click.echo(f"\n  ✗ {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"\n  Error: {e}", err=True)
        sys.exit(1)


@execute.command("status")
def execute_status():
    """Show order history for this session."""
    _setup_logging("WARNING")
    from nae.agents.execution_adapter import ExecutionAdapter

    adapter = ExecutionAdapter()
    orders = adapter.get_order_history()

    if not orders:
        click.echo("\n  No orders in this session.")
        return

    click.echo(f"\n  Orders ({len(orders)}):")
    for o in orders:
        click.echo(f"    {o['order_id']}  {o['side']} {o['quantity']} {o['symbol']}  [{o['status']}]")


# ── CONFIG ──────────────────────────────────────────────────────

@cli.group()
def config():
    """View and manage NAE configuration."""
    pass


@config.command("show")
def config_show():
    """Display current configuration."""
    from nae.core.feature_gates import get_gates

    gates = get_gates()
    click.echo("\n  Current configuration:")
    click.echo(f"  {'─' * 50}")
    _print_config(gates.config, indent=2)


def _print_config(d: dict, indent: int = 0) -> None:
    prefix = " " * indent
    for k, v in d.items():
        if isinstance(v, dict):
            click.echo(f"{prefix}  {k}:")
            _print_config(v, indent + 2)
        else:
            display = v if v is not None else "(not set)"
            # Mask API keys
            if "key" in k.lower() or "secret" in k.lower():
                if v and isinstance(v, str) and len(v) > 8:
                    display = v[:4] + "..." + v[-4:]
            click.echo(f"{prefix}  {k:30s} {display}")


@config.command("path")
def config_path():
    """Show the config file path being used."""
    from nae.core.feature_gates import get_gates

    gates = get_gates()
    if gates._config_path:
        click.echo(f"\n  Config: {gates._config_path}")
    else:
        click.echo("\n  No config file found. Run 'nae init' to create one.")


def main():
    cli()


if __name__ == "__main__":
    main()
