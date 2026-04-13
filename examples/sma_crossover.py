"""
EXAMPLE STRATEGY — FOR DEMONSTRATION PURPOSES ONLY

Simple Moving Average Crossover

This is a basic educational example of a trend-following strategy.
It is NOT optimized, NOT tested for profitability, and is NOT
a recommendation. Users must develop and test their own strategies.

Logic:
  Enter when short SMA crosses above long SMA.
  Exit when short SMA crosses below long SMA.
"""

PARAMS = {
    "short_window": 20,
    "long_window": 50,
}


def should_enter(data: dict) -> bool:
    """Enter when the 20-period SMA is above the 50-period SMA."""
    sma_short = data.get("sma_20")
    sma_long = data.get("sma_50")
    if sma_short is None or sma_long is None:
        return False
    return sma_short > sma_long


def should_exit(data: dict) -> bool:
    """Exit when the 20-period SMA crosses below the 50-period SMA."""
    sma_short = data.get("sma_20")
    sma_long = data.get("sma_50")
    if sma_short is None or sma_long is None:
        return False
    return sma_short < sma_long


def position_size(data: dict, capital: float) -> int:
    """Fixed position size: invest 10% of capital per trade."""
    price = data.get("close", 1)
    if price <= 0:
        return 0
    allocation = capital * 0.10
    return max(1, int(allocation / price))
