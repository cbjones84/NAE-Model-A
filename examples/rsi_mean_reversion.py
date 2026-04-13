"""
EXAMPLE STRATEGY — FOR DEMONSTRATION PURPOSES ONLY

RSI Mean Reversion

This is a basic educational example of a mean-reversion strategy.
It is NOT optimized, NOT tested for profitability, and is NOT
a recommendation. Users must develop and test their own strategies.

Logic:
  Enter when RSI drops below oversold threshold (< 30).
  Exit when RSI rises above overbought threshold (> 70).
"""

PARAMS = {
    "oversold_threshold": 30,
    "overbought_threshold": 70,
}


def should_enter(data: dict) -> bool:
    """Enter when RSI is below the oversold threshold."""
    rsi = data.get("rsi_14")
    if rsi is None:
        return False
    return rsi < PARAMS["oversold_threshold"]


def should_exit(data: dict) -> bool:
    """Exit when RSI is above the overbought threshold."""
    rsi = data.get("rsi_14")
    if rsi is None:
        return False
    return rsi > PARAMS["overbought_threshold"]


def position_size(data: dict, capital: float) -> int:
    """Fixed position size: invest 5% of capital per trade."""
    price = data.get("close", 1)
    if price <= 0:
        return 0
    allocation = capital * 0.05
    return max(1, int(allocation / price))
