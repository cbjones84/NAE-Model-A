"""
NAE Research Engine (derived from Ralph architecture)

Provides AI-assisted market research and data analysis.
All output is raw research data — no trade recommendations,
no signals, no "best" or "recommended" labels.

The user interprets all results and makes their own decisions.
"""

import os
import datetime
import json
import hashlib
import statistics
import logging
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, asdict, field
from enum import Enum
from pathlib import Path

logger = logging.getLogger("nae.research")


class DataSource(Enum):
    YAHOO_FINANCE = "yahoo_finance"
    ALPHA_VANTAGE = "alpha_vantage"
    USER_IMPORT = "user_import"


@dataclass
class MarketDataPoint:
    """OHLCV market data point."""
    symbol: str
    timestamp: str
    open_price: float
    high_price: float
    low_price: float
    close_price: float
    volume: int
    source: str

    @property
    def data_hash(self) -> str:
        raw = f"{self.symbol}{self.timestamp}{self.close_price}{self.volume}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]


@dataclass
class ResearchReport:
    """Structured research output — informational only."""
    symbol: str
    generated_at: str
    period_days: int
    data_points: int
    metrics: Dict[str, float] = field(default_factory=dict)
    patterns: List[str] = field(default_factory=list)
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class ResearchEngine:
    """
    AI-assisted market research engine.

    Capabilities:
    - Fetch and normalize OHLCV data (via yfinance or user-imported CSV)
    - Compute statistical metrics (volatility, correlation, moving averages)
    - Detect technical patterns (user interprets significance)
    - Generate structured research reports (JSON/CSV)

    This engine does NOT:
    - Generate trade signals or recommendations
    - Score strategies by "profitability"
    - Suggest entry/exit points
    - Provide any form of financial advice
    """

    def __init__(self, data_dir: str = "./data", report_dir: str = "./reports"):
        self.data_dir = Path(data_dir)
        self.report_dir = Path(report_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.report_dir.mkdir(parents=True, exist_ok=True)
        self._yf = None

    def _get_yfinance(self):
        if self._yf is None:
            try:
                import yfinance as yf
                self._yf = yf
            except ImportError as e:
                raise ImportError(
                    "yfinance is required for live data. "
                    "Install with: pip install yfinance"
                ) from e
        return self._yf

    def fetch_market_data(
        self,
        symbol: str,
        period: str = "1y",
        interval: str = "1d",
    ) -> List[MarketDataPoint]:
        """
        Fetch OHLCV data for a symbol.

        Args:
            symbol: Ticker symbol (e.g. 'SPY', 'BTC-USD')
            period: Data period ('1mo', '3mo', '6mo', '1y', '2y', '5y')
            interval: Bar interval ('1d', '1wk', '1mo')

        Returns:
            List of MarketDataPoint objects
        """
        yf = self._get_yfinance()
        ticker = yf.Ticker(symbol)
        df = ticker.history(period=period, interval=interval)

        if df.empty:
            logger.warning(f"No data returned for {symbol}")
            return []

        points = []
        for ts, row in df.iterrows():
            points.append(MarketDataPoint(
                symbol=symbol,
                timestamp=str(ts),
                open_price=float(row["Open"]),
                high_price=float(row["High"]),
                low_price=float(row["Low"]),
                close_price=float(row["Close"]),
                volume=int(row["Volume"]),
                source="yahoo_finance",
            ))

        logger.info(f"Fetched {len(points)} data points for {symbol}")
        return points

    def import_csv(self, filepath: str, symbol: str) -> List[MarketDataPoint]:
        """
        Import OHLCV data from a user-provided CSV file.

        Expected columns: date, open, high, low, close, volume
        """
        import csv

        points = []
        with open(filepath, "r") as f:
            reader = csv.DictReader(f)
            for row in reader:
                points.append(MarketDataPoint(
                    symbol=symbol,
                    timestamp=row.get("date", row.get("Date", "")),
                    open_price=float(row.get("open", row.get("Open", 0))),
                    high_price=float(row.get("high", row.get("High", 0))),
                    low_price=float(row.get("low", row.get("Low", 0))),
                    close_price=float(row.get("close", row.get("Close", 0))),
                    volume=int(float(row.get("volume", row.get("Volume", 0)))),
                    source="user_import",
                ))

        logger.info(f"Imported {len(points)} data points from {filepath}")
        return points

    def compute_metrics(self, data: List[MarketDataPoint]) -> Dict[str, float]:
        """
        Compute statistical metrics from market data.

        Returns a dictionary of descriptive statistics.
        These are mathematical facts about the data, not recommendations.
        """
        if len(data) < 2:
            return {"error": -1, "message_code": 0}

        closes = [p.close_price for p in data]
        returns = [
            (closes[i] - closes[i - 1]) / closes[i - 1]
            for i in range(1, len(closes))
            if closes[i - 1] != 0
        ]

        if not returns:
            return {}

        metrics = {
            "data_points": len(data),
            "period_start": data[0].timestamp,
            "period_end": data[-1].timestamp,
            "price_start": closes[0],
            "price_end": closes[-1],
            "price_change_pct": ((closes[-1] - closes[0]) / closes[0]) * 100,
            "avg_daily_return_pct": statistics.mean(returns) * 100,
            "std_daily_return_pct": statistics.stdev(returns) * 100 if len(returns) > 1 else 0,
            "max_daily_return_pct": max(returns) * 100,
            "min_daily_return_pct": min(returns) * 100,
            "high_price": max(closes),
            "low_price": min(closes),
            "avg_volume": statistics.mean([p.volume for p in data]),
        }

        # Annualized volatility (descriptive statistic)
        if len(returns) > 1:
            metrics["annualized_volatility_pct"] = statistics.stdev(returns) * (252 ** 0.5) * 100

        # Simple moving averages (mathematical computation)
        for window in [20, 50, 200]:
            if len(closes) >= window:
                sma = statistics.mean(closes[-window:])
                metrics[f"sma_{window}"] = round(sma, 4)

        # Max drawdown (descriptive statistic)
        peak = closes[0]
        max_dd = 0.0
        for c in closes:
            if c > peak:
                peak = c
            dd = (peak - c) / peak if peak != 0 else 0
            if dd > max_dd:
                max_dd = dd
        metrics["max_drawdown_pct"] = max_dd * 100

        return metrics

    def detect_patterns(self, data: List[MarketDataPoint]) -> List[str]:
        """
        Detect basic technical patterns in price data.

        Returns a list of factual pattern observations.
        The user determines whether any pattern is actionable.
        """
        if len(data) < 50:
            return ["Insufficient data for pattern detection (need 50+ bars)"]

        closes = [p.close_price for p in data]
        patterns = []

        # SMA crossover observation
        if len(closes) >= 50:
            sma_20 = statistics.mean(closes[-20:])
            sma_50 = statistics.mean(closes[-50:])
            prev_sma_20 = statistics.mean(closes[-21:-1])
            prev_sma_50 = statistics.mean(closes[-51:-1])

            if prev_sma_20 <= prev_sma_50 and sma_20 > sma_50:
                patterns.append("SMA 20/50 crossover observed (20 crossed above 50)")
            elif prev_sma_20 >= prev_sma_50 and sma_20 < sma_50:
                patterns.append("SMA 20/50 crossover observed (20 crossed below 50)")

        # Volatility regime observation
        recent_returns = [
            (closes[i] - closes[i - 1]) / closes[i - 1]
            for i in range(max(1, len(closes) - 20), len(closes))
            if closes[i - 1] != 0
        ]
        if recent_returns:
            recent_vol = statistics.stdev(recent_returns) if len(recent_returns) > 1 else 0
            all_returns = [
                (closes[i] - closes[i - 1]) / closes[i - 1]
                for i in range(1, len(closes))
                if closes[i - 1] != 0
            ]
            avg_vol = statistics.stdev(all_returns) if len(all_returns) > 1 else 0.01

            if avg_vol > 0:
                vol_ratio = recent_vol / avg_vol
                if vol_ratio > 1.5:
                    patterns.append(
                        f"Elevated volatility period (recent vol {vol_ratio:.1f}x average)"
                    )
                elif vol_ratio < 0.5:
                    patterns.append(
                        f"Low volatility period (recent vol {vol_ratio:.1f}x average)"
                    )

        # Price relative to moving averages
        if len(closes) >= 200:
            sma_200 = statistics.mean(closes[-200:])
            current = closes[-1]
            pct_from_sma = ((current - sma_200) / sma_200) * 100
            patterns.append(f"Price is {pct_from_sma:+.1f}% from 200-day SMA")

        if not patterns:
            patterns.append("No notable patterns detected in current data")

        return patterns

    def generate_report(
        self,
        symbol: str,
        period: str = "1y",
        export_format: str = "json",
    ) -> ResearchReport:
        """
        Generate a full research report for a symbol.

        The report contains factual data and statistical observations.
        It does NOT contain trade recommendations or advice.
        """
        data = self.fetch_market_data(symbol, period=period)
        metrics = self.compute_metrics(data)
        patterns = self.detect_patterns(data)

        report = ResearchReport(
            symbol=symbol,
            generated_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
            period_days=len(data),
            data_points=len(data),
            metrics=metrics,
            patterns=patterns,
            notes="Research data only — not a trade recommendation.",
        )

        # Export
        filename = f"{symbol}_{datetime.date.today().isoformat()}"
        if export_format == "json":
            outpath = self.report_dir / f"{filename}.json"
            with open(outpath, "w") as f:
                json.dump(report.to_dict(), f, indent=2, default=str)
        elif export_format == "csv":
            outpath = self.report_dir / f"{filename}_metrics.csv"
            import csv
            with open(outpath, "w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(["metric", "value"])
                for k, v in metrics.items():
                    writer.writerow([k, v])

        logger.info(f"Report generated: {outpath}")
        return report

    def scan_multiple(
        self,
        symbols: List[str],
        period: str = "1y",
    ) -> List[ResearchReport]:
        """Run research reports for multiple symbols."""
        reports = []
        for sym in symbols:
            try:
                r = self.generate_report(sym, period=period)
                reports.append(r)
            except Exception as e:
                logger.error(f"Failed to generate report for {sym}: {e}")
        return reports

    def correlation_matrix(
        self,
        symbols: List[str],
        period: str = "1y",
    ) -> Dict[str, Dict[str, float]]:
        """
        Compute pairwise correlation matrix for a list of symbols.

        Returns a nested dict of correlation coefficients.
        These are mathematical facts, not trading signals.
        """
        all_data: Dict[str, List[float]] = {}
        min_len = float("inf")

        for sym in symbols:
            data = self.fetch_market_data(sym, period=period)
            closes = [p.close_price for p in data]
            returns = [
                (closes[i] - closes[i - 1]) / closes[i - 1]
                for i in range(1, len(closes))
                if closes[i - 1] != 0
            ]
            all_data[sym] = returns
            if len(returns) < min_len:
                min_len = len(returns)

        # Trim to common length
        for sym in all_data:
            all_data[sym] = all_data[sym][:int(min_len)]

        # Compute correlations
        matrix: Dict[str, Dict[str, float]] = {}
        for s1 in symbols:
            matrix[s1] = {}
            for s2 in symbols:
                if s1 == s2:
                    matrix[s1][s2] = 1.0
                elif len(all_data.get(s1, [])) > 1 and len(all_data.get(s2, [])) > 1:
                    n = min(len(all_data[s1]), len(all_data[s2]))
                    x, y = all_data[s1][:n], all_data[s2][:n]
                    mean_x, mean_y = statistics.mean(x), statistics.mean(y)
                    cov = sum((a - mean_x) * (b - mean_y) for a, b in zip(x, y)) / (n - 1)
                    std_x = statistics.stdev(x)
                    std_y = statistics.stdev(y)
                    if std_x > 0 and std_y > 0:
                        matrix[s1][s2] = round(cov / (std_x * std_y), 4)
                    else:
                        matrix[s1][s2] = 0.0
                else:
                    matrix[s1][s2] = 0.0

        return matrix
