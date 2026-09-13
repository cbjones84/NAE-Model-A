"""Market data helpers.

Default live source is Yahoo Finance via ``yfinance`` (internet required).
CSV import supports offline / user-provided OHLCV. This package is the
layout advertised as ``nae/tools/data/``. There is no NAE cloud data plane.
"""

from typing import List, Optional

__all__ = [
    "MarketDataPoint",
    "fetch_market_data",
    "import_csv",
    "last_close",
]


def __getattr__(name: str):
    if name == "MarketDataPoint":
        from nae.agents.research_engine import MarketDataPoint
        return MarketDataPoint
    raise AttributeError(name)


def fetch_market_data(
    symbol: str,
    period: str = "1y",
    interval: str = "1d",
) -> List:
    """Fetch OHLCV bars. Requires network access to Yahoo Finance."""
    from nae.agents.research_engine import ResearchEngine
    return ResearchEngine().fetch_market_data(symbol, period=period, interval=interval)


def import_csv(filepath: str, symbol: str) -> List:
    """Load OHLCV from a user CSV (columns: date, open, high, low, close, volume)."""
    from nae.agents.research_engine import ResearchEngine
    return ResearchEngine().import_csv(filepath, symbol)


def last_close(symbol: str) -> Optional[float]:
    """Return the most recent Yahoo Finance daily close, or None on failure."""
    try:
        import yfinance as yf
    except ImportError:
        return None
    try:
        df = yf.Ticker(symbol).history(period="5d", interval="1d")
    except Exception:
        return None
    if df is None or df.empty or "Close" not in df.columns:
        return None
    try:
        return float(df["Close"].iloc[-1])
    except (IndexError, TypeError, ValueError):
        return None
