"""
STRATEGY TEMPLATE — Starting Point for Your Own Strategy

Copy this file to your strategies/ directory, rename it, and
implement your own entry/exit logic.

IMPORTANT: This is a blank template. It does NOTHING by default.
NAE does not endorse, recommend, or guarantee the performance of
any strategy. You are solely responsible for all trading decisions.

Required hooks:
  should_enter(data) -> bool
  should_exit(data) -> bool

Optional hooks:
  position_size(data, capital) -> int
  on_data(data) -> None
  filter(symbol) -> bool

Available data fields (provided by the backtest engine):
  data['open']     - Opening price
  data['high']     - High price
  data['low']      - Low price
  data['close']    - Closing price
  data['volume']   - Volume
  data['sma_20']   - 20-period Simple Moving Average (if enough data)
  data['sma_50']   - 50-period Simple Moving Average (if enough data)
  data['sma_200']  - 200-period Simple Moving Average (if enough data)
  data['rsi_14']   - 14-period RSI (if enough data)
"""


# ─── Your Parameters ──────────────────────────────────────────
# Define configurable parameters for your strategy here.

PARAMS = {
    # Add your parameters
    # Example: "lookback": 20,
    # Example: "threshold": 0.02,
}


# ─── Required: Entry Logic ────────────────────────────────────

def should_enter(data: dict) -> bool:
    """
    Return True when YOUR entry conditions are met.

    Implement your logic here. Examples:
      - Moving average crossover
      - RSI threshold
      - Volume spike
      - Custom indicator
    """
    # TODO: Implement your entry logic
    return False


# ─── Required: Exit Logic ─────────────────────────────────────

def should_exit(data: dict) -> bool:
    """
    Return True when YOUR exit conditions are met.

    Implement your logic here. Examples:
      - Take profit at X%
      - Stop loss at Y%
      - Indicator reversal
      - Time-based exit
    """
    # TODO: Implement your exit logic
    return False


# ─── Optional: Position Sizing ────────────────────────────────

def position_size(data: dict, capital: float) -> int:
    """
    Return the number of shares/contracts to trade.

    Default: 1 share. Override with your own sizing logic.
    Examples:
      - Fixed dollar amount
      - Percentage of capital
      - Volatility-based sizing
    """
    return 1
