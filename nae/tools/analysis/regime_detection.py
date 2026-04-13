"""
NAE Market Regime Detection

Detects statistical market regimes from price data:
- Low volatility
- Trending (up/down)
- Mean-reverting
- High volatility / crisis

These are mathematical classifications of historical data.
They are NOT trade signals or recommendations.
The user decides how to interpret regime information.
"""

import statistics
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
from datetime import datetime


class MarketRegime(Enum):
    LOW_VOLATILITY = "low_volatility"
    TRENDING_UP = "trending_up"
    TRENDING_DOWN = "trending_down"
    MEAN_REVERTING = "mean_reverting"
    HIGH_VOLATILITY = "high_volatility"
    CRISIS = "crisis"


@dataclass
class RegimeAnalysis:
    """Regime detection result — informational only."""
    symbol: str
    regime: MarketRegime
    confidence: float
    features: Dict[str, float]
    analyzed_at: str
    note: str = "Regime classification is a statistical observation, not a trade signal."


class RegimeDetector:
    """
    Classifies market conditions using statistical features.

    Uses realized volatility, trend strength, and mean-reversion
    scores to classify the current regime. All outputs are
    descriptive statistics — no actionable recommendations.
    """

    def __init__(self):
        self.history: List[Tuple[str, MarketRegime]] = []

    def detect(self, closes: List[float], symbol: str = "UNKNOWN") -> RegimeAnalysis:
        """
        Detect the current market regime from a list of closing prices.

        Args:
            closes: list of closing prices (oldest first)
            symbol: ticker symbol for labeling

        Returns:
            RegimeAnalysis with detected regime and features
        """
        if len(closes) < 50:
            return RegimeAnalysis(
                symbol=symbol,
                regime=MarketRegime.LOW_VOLATILITY,
                confidence=0.0,
                features={"error": -1},
                analyzed_at=datetime.utcnow().isoformat(),
                note="Insufficient data (need 50+ bars)",
            )

        returns = [
            (closes[i] - closes[i - 1]) / closes[i - 1]
            for i in range(1, len(closes))
            if closes[i - 1] != 0
        ]

        # Features
        vol_20 = statistics.stdev(returns[-20:]) if len(returns) >= 20 else 0
        vol_full = statistics.stdev(returns) if len(returns) > 1 else 0.01
        vol_ratio = vol_20 / vol_full if vol_full > 0 else 1.0

        # Trend: linear regression slope approximation
        n = min(50, len(returns))
        recent = returns[-n:]
        cum_return = sum(recent)
        trend_strength = cum_return / n if n > 0 else 0

        # Mean reversion: autocorrelation lag-1
        mean_r = statistics.mean(recent)
        if len(recent) > 2:
            num = sum(
                (recent[i] - mean_r) * (recent[i - 1] - mean_r)
                for i in range(1, len(recent))
            )
            den = sum((r - mean_r) ** 2 for r in recent)
            autocorr = num / den if den != 0 else 0
        else:
            autocorr = 0

        features = {
            "volatility_20d": round(vol_20, 6),
            "volatility_full": round(vol_full, 6),
            "volatility_ratio": round(vol_ratio, 4),
            "trend_strength": round(trend_strength, 6),
            "autocorrelation_lag1": round(autocorr, 4),
            "cumulative_return_50d": round(cum_return, 4),
        }

        # Classification
        regime, confidence = self._classify(features)

        analysis = RegimeAnalysis(
            symbol=symbol,
            regime=regime,
            confidence=round(confidence, 2),
            features=features,
            analyzed_at=datetime.utcnow().isoformat(),
        )

        self.history.append((analysis.analyzed_at, regime))
        return analysis

    @staticmethod
    def _classify(features: Dict[str, float]) -> Tuple[MarketRegime, float]:
        vol_ratio = features.get("volatility_ratio", 1.0)
        trend = features.get("trend_strength", 0)
        autocorr = features.get("autocorrelation_lag1", 0)

        # Crisis: very high volatility
        if vol_ratio > 2.5:
            return MarketRegime.CRISIS, min(0.95, vol_ratio / 3.0)

        # High volatility
        if vol_ratio > 1.8:
            return MarketRegime.HIGH_VOLATILITY, min(0.9, vol_ratio / 2.5)

        # Strong trend
        if abs(trend) > 0.003:
            if trend > 0:
                return MarketRegime.TRENDING_UP, min(0.9, abs(trend) / 0.005)
            else:
                return MarketRegime.TRENDING_DOWN, min(0.9, abs(trend) / 0.005)

        # Mean reverting: negative autocorrelation
        if autocorr < -0.15:
            return MarketRegime.MEAN_REVERTING, min(0.85, abs(autocorr))

        # Low volatility
        if vol_ratio < 0.7:
            return MarketRegime.LOW_VOLATILITY, min(0.85, 1.0 - vol_ratio)

        # Default: low confidence classification
        return MarketRegime.LOW_VOLATILITY, 0.3
