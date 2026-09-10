# NAE Platform — Trading Research Toolkit

**Your data. Your control. Your privacy.**

NAE Platform is a self-hosted **research and analysis toolkit**. It helps you
fetch market data, compute statistics, detect simple technical patterns,
classify volatility/trend regimes, and backtest **your own** Python
strategies. Optional broker order relay (Tradier or Alpaca) is off by default.

This is **not** an AI advisor, LLM copilot, or portfolio manager. Analysis is
ordinary statistics and heuristics. All trading decisions are yours.

> **Important:** NAE does not provide financial advice, trade recommendations,
> or portfolio management. See `legal/RISK_DISCLOSURE.md` before using.

---

## Features

- **Market research** — Fetch OHLCV (Yahoo Finance by default; internet
  required) or import a CSV. Metrics, pattern observations, pairwise
  correlations (Pro), and regime classification (Pro).
- **Strategy backtesting** — Run user-authored `should_enter` / `should_exit`
  strategies. Reports Sharpe, drawdown, win rate, and related figures.
  Requires `nae.mode: backtest` or `full`.
- **Broker integration** — Optionally connect to Tradier or Alpaca for
  user-initiated orders. Requires `nae.mode: full` **and**
  `execution_enabled: true`. Disabled by default; paper mode on by default.
- **Runs on your machine** — The application has no NAE cloud backend and
  sends no product telemetry. Default market data still comes from
  **Yahoo Finance**. Enabled execution talks to **your broker’s API**.
- **CLI-first** — Scriptable commands; no web UI.

## Quick Start

### Option 1: Install from Source

```bash
# Clone the repo
git clone <your-repo-url> nae-platform
cd nae-platform

# Install
pip install .

# Initialize workspace
nae init

# Run your first research scan
nae research scan --asset SPY
```

### Option 2: Docker

```bash
# Build
docker-compose build

# Initialize
docker-compose run nae init

# Research
docker-compose run nae research scan --asset SPY
```

## Operating modes (enforced)

Set `nae.mode` in `config.yaml`. This is **not** display-only:

| Mode | Research | Backtest | Execute |
|------|:--------:|:--------:|:-------:|
| `research_only` (default) | yes | no | no |
| `backtest` | yes | yes | no |
| `full` | yes | yes | only if `execution_enabled: true` and a broker is configured |

`research_only` blocks execute **even if** `execution_enabled` is true.

## CLI Commands

### System
```bash
nae init                              # Initialize workspace + accept terms
nae status                            # System health and configuration
```

### Research
```bash
nae research scan --asset SPY         # Statistical report (Yahoo Finance)
nae research patterns --asset BTC-USD # Pattern observations
nae research correlations --assets SPY,QQQ,AAPL   # Pro
nae research regime --asset SPY       # Regime classification (Pro)
nae research import --file ./data/spy.csv --symbol SPY
```

CSV import expects columns: `date, open, high, low, close, volume`.

### Strategy Management
```bash
nae strategy create my_strategy       # Create from template
nae strategy validate ./strategies/my_strategy.py
nae strategy list                     # List all strategies
```

### Backtesting
Requires `nae.mode: backtest` or `full`.

```bash
nae backtest run ./strategies/my_strategy.py --symbols SPY --capital 100000
nae backtest run ./strategies/my_strategy.py --symbols SPY,AAPL --start 2025-01-01 --end 2025-12-31
nae backtest run ./strategies/my_strategy.py --symbols SPY --export ./reports/result.json
```

Multi-symbol backtests require a Pro (or Team) license.

### Execution (Disabled by Default)
Requires `nae.mode: full` **and** `execution_enabled: true`.

```bash
nae execute enable                    # Show enable instructions
nae execute order --asset SPY --side buy --qty 10 --type limit --price 450
nae execute status                    # Order history from logs/execution_audit.jsonl
```

### Configuration
```bash
nae config show                       # Display current config
nae config path                       # Show config file location
```

### License
```bash
nae license show                      # Show current tier and expiry
nae license verify ./license.nae      # Dry-run check a file without activating
nae license activate ./license.nae    # Install a license file
nae license deactivate                # Remove license from this machine
nae license machine-id                # Print this machine's binding id
```

See [`docs/licensing.md`](docs/licensing.md) for the implemented feature map.
Walk-forward, Monte Carlo, and benchmark comparison are **not implemented**.

## Configuration

Copy `config.example.yaml` to `config.yaml` and edit:

```yaml
nae:
  mode: research_only          # research_only | backtest | full (enforced)
  execution_enabled: false     # Must explicitly enable; still needs mode=full

broker:
  name: tradier                  # or: alpaca
  api_key: your_api_key_here
  sandbox: true                  # Start with paper trading
```

## Writing Strategies

Strategies are Python files with two required hooks:

```python
def should_enter(data: dict) -> bool:
    """Return True when YOUR entry conditions are met."""
    return data.get("sma_20", 0) > data.get("sma_50", 0)

def should_exit(data: dict) -> bool:
    """Return True when YOUR exit conditions are met."""
    return data.get("sma_20", 0) < data.get("sma_50", 0)
```

See `examples/` for educational examples and `examples/strategy_template.py`
for a blank starting point. Examples are **not** recommendations.

### Available Data Fields

| Field      | Description                    |
|------------|--------------------------------|
| `open`     | Opening price                  |
| `high`     | High price                     |
| `low`      | Low price                      |
| `close`    | Closing price                  |
| `volume`   | Volume                         |
| `sma_20`   | 20-period Simple Moving Average|
| `sma_50`   | 50-period Simple Moving Average|
| `sma_200`  | 200-period Simple Moving Average|
| `rsi_14`   | 14-period RSI                  |

## Project Structure

```
nae-platform/
├── nae/
│   ├── agents/              # Research engine, execution adapter, validator, monitor
│   ├── core/                # Feature gates, disclaimers, licensing
│   ├── strategies/          # Static strategy validation
│   ├── tools/
│   │   ├── backtesting/     # Backtest engine
│   │   ├── analysis/        # Regime detection
│   │   └── data/            # OHLCV fetch / CSV helpers (Yahoo Finance)
│   └── cli/                 # Command-line interface
├── examples/                # Educational strategy examples
├── legal/                   # Terms of Service, Risk Disclosure
├── docs/                    # Licensing and issuance notes
├── tests/
├── config.example.yaml      # Configuration template
├── Dockerfile
├── docker-compose.yml
└── requirements.txt
```

## Legal

- **Terms of Service:** `legal/TERMS_OF_SERVICE.md`
- **Risk Disclosure:** `legal/RISK_DISCLOSURE.md`

NAE Platform is a software tool. It is not registered with the SEC, FINRA,
CFTC, or any regulatory body. It does not provide financial advice.

All trading involves risk. Past backtest performance does not indicate
future results.

---

**NAE Platform** — Research infrastructure for traders who want control.
