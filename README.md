# NAE Platform — AI-Assisted Trading Research Infrastructure

**Your AI. Your Control. Your Privacy.**

NAE Platform is a self-hosted research and analysis tool that enables you to
design, test, and manage your own trading strategies. NAE provides AI-assisted
analytics, backtesting, and optional broker integration — all under your
control.

> **Important:** NAE does not provide financial advice, trade recommendations,
> or portfolio management. All trading decisions are made solely by you.
> See `legal/RISK_DISCLOSURE.md` before using.

---

## Features

- **Market Research** — Fetch and analyze OHLCV data with statistical metrics,
  pattern detection, correlation analysis, and regime classification
- **Strategy Backtesting** — Test your own strategies against historical data
  with Sharpe ratio, drawdown, win rate, and other performance metrics
- **Broker Integration** — Optionally connect to Tradier or Alpaca for
  user-controlled order execution (disabled by default)
- **Self-Hosted** — All data stays on your infrastructure. No cloud dependency.
- **CLI-First** — Lightweight, scriptable, and automation-friendly

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

## CLI Commands

### System
```bash
nae init                              # Initialize workspace + accept terms
nae status                            # System health and configuration
```

### Research
```bash
nae research scan --asset SPY         # Full research report
nae research patterns --asset BTC-USD # Pattern detection
nae research correlations --assets SPY,QQQ,AAPL
nae research regime --asset SPY       # Market regime detection
```

### Strategy Management
```bash
nae strategy create my_strategy       # Create from template
nae strategy validate ./strategies/my_strategy.py
nae strategy list                     # List all strategies
```

### Backtesting
```bash
nae backtest run ./strategies/my_strategy.py --symbols SPY --capital 100000
nae backtest run ./strategies/my_strategy.py --symbols SPY,AAPL --start 2025-01-01 --end 2025-12-31
nae backtest run ./strategies/my_strategy.py --symbols SPY --export ./reports/result.json
```

### Execution (Disabled by Default)
```bash
nae execute enable                    # Show enable instructions
nae execute order --asset SPY --side buy --qty 10 --type limit --price 450
nae execute status                    # Show order history
```

### Configuration
```bash
nae config show                       # Display current config
nae config path                       # Show config file location
```

### License
```bash
nae license show                      # Show current tier and expiry
nae license activate ./license.nae    # Install a license file
nae license deactivate                # Remove license from this machine
nae license machine-id                # Print this machine's binding id
```

See [`docs/licensing.md`](docs/licensing.md) for the full licensing
model (tiers, feature map, offline verification, and rotation).

## Configuration

Copy `config.example.yaml` to `config.yaml` and edit:

```yaml
nae:
  mode: research_only
  execution_enabled: false       # Must explicitly enable

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
for a blank starting point.

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
NAE Model A/
├── nae/
│   ├── agents/              # Research engine, execution adapter, validator, monitor
│   ├── core/                # Feature gates, disclaimers
│   ├── tools/
│   │   ├── backtesting/     # Backtest engine
│   │   ├── analysis/        # Regime detection
│   │   └── data/            # Data fetching
│   └── cli/                 # Command-line interface
├── examples/                # Educational strategy examples
├── legal/                   # Terms of Service, Risk Disclosure
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
