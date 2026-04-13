"""
EXAMPLE STRATEGY — FOR DEMONSTRATION PURPOSES ONLY

Bollinger Band Strategy

This is a basic educational example of a volatility-based strategy.
It is NOT optimized, NOT tested for profitability, and is NOT
a recommendation. Users must develop and test their own strategies.

Logic:
  Enter when price drops below the lower Bollinger Band.
  Exit when price rises above the upper Bollinger Band.

Note: The backtest engine provides sma_20. This strategy
computes Bollinger Bands from that and recent price data.
"""

import statistics

PARAMS = {
    "window": 20,
    "num_std": 2.0,
}


def _compute_bands(data: dict) -> tuple:
    """Compute upper and lower Bollinger Bands."""
    sma = data.get("sma_20")
    if sma is None:
        return None, None

    # Approximate std dev from available data
    # In a real implementation, you'd have access to the full price history
    close = data.get("close", 0)
    high = data.get("high", close)
    low = data.get("low", close)

    # Simple range-based volatility approximation
    price_range = high - low
    approx_std = price_range * 0.5 if price_range > 0 else sma * 0.02

    upper = sma + (PARAMS["num_std"] * approx_std)
    lower = sma - (PARAMS["num_std"] * approx_std)
    return upper, lower


def should_enter(data: dict) -> bool:
    """Enter when price drops below the lower Bollinger Band."""
    upper, lower = _compute_bands(data)
    if lower is None:
        return False
    return data.get("close", 0) < lower


def should_exit(data: dict) -> bool:
    """Exit when price rises above the upper Bollinger Band."""
    upper, lower = _compute_bands(data)
    if upper is None:
        return False
    return data.get("close", 0) > upper


def position_size(data: dict, capital: float) -> int:
    """Fixed position size: invest 5% of capital per trade."""
    price = data.get("close", 1)
    if price <= 0:
        return 0
    allocation = capital * 0.05
    return max(1, int(allocation / price))
