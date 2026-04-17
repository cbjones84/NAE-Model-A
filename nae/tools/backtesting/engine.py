"""
NAE Simple Backtest Engine

Event-driven backtester that runs user-defined strategies against
historical data. Returns raw performance metrics for user interpretation.

No strategy scoring, no ranking, no recommendations.
Results are mathematical computations on historical data.
Past performance does not indicate future results.
"""

import datetime
import statistics
import logging
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass, field, asdict

logger = logging.getLogger("nae.backtest")


@dataclass
class BacktestResult:
    """Raw backtest output — mathematical facts about historical simulation."""
    strategy_name: str
    symbols: List[str]
    start_date: str
    end_date: str
    initial_capital: float
    final_capital: float
    total_return_pct: float
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate_pct: float
    avg_trade_return_pct: float
    max_drawdown_pct: float
    sharpe_ratio: float
    sortino_ratio: float
    volatility_annual_pct: float
    data_points_used: int
    engine: str = "nae_simple"
    disclaimer: str = "Historical simulation only — not indicative of future results."

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def summary(self) -> str:
        lines = [
            f"Backtest: {self.strategy_name}",
            f"Symbols: {', '.join(self.symbols)}",
            f"Period: {self.start_date} → {self.end_date}",
            f"Data points: {self.data_points_used}",
            "",
            f"Initial capital:  ${self.initial_capital:>12,.2f}",
            f"Final capital:    ${self.final_capital:>12,.2f}",
            f"Total return:     {self.total_return_pct:>11.2f}%",
            "",
            f"Total trades:     {self.total_trades:>5}",
            f"Win rate:         {self.win_rate_pct:>11.2f}%",
            f"Avg trade return: {self.avg_trade_return_pct:>11.2f}%",
            "",
            f"Max drawdown:     {self.max_drawdown_pct:>11.2f}%",
            f"Sharpe ratio:     {self.sharpe_ratio:>11.4f}",
            f"Sortino ratio:    {self.sortino_ratio:>11.4f}",
            f"Annual volatility:{self.volatility_annual_pct:>11.2f}%",
            "",
            f"⚠ {self.disclaimer}",
        ]
        return "\n".join(lines)


class SimpleBacktestEngine:
    """
    Simple event-driven backtester.

    Iterates through historical bars, calls the user's strategy hooks,
    and tracks paper positions. Returns raw performance metrics.
    """

    def run(
        self,
        strategy: Dict[str, Any],
        symbols: List[str],
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        initial_capital: float = 100_000.0,
    ) -> Dict[str, Any]:
        """
        Run a backtest with the user's strategy.

        Args:
            strategy: dict with 'entry_fn', 'exit_fn', 'size_fn', 'name', 'params'
            symbols: list of ticker symbols to test
            start_date: ISO date string (YYYY-MM-DD)
            end_date: ISO date string (YYYY-MM-DD)
            initial_capital: starting capital for simulation

        Returns:
            BacktestResult as a dict
        """
        entry_fn: Callable = strategy["entry_fn"]
        exit_fn: Callable = strategy["exit_fn"]
        size_fn: Callable = strategy.get("size_fn", lambda d, c: 1)
        name = strategy.get("name", "unnamed_strategy")

        all_trades: List[Dict[str, float]] = []
        equity_curve: List[float] = [initial_capital]
        capital = initial_capital
        total_data_points = 0

        for symbol in symbols:
            data = self._fetch_data(symbol, start_date, end_date)
            if len(data) < 20:
                logger.warning(f"Insufficient data for {symbol} ({len(data)} bars)")
                continue

            total_data_points += len(data)
            position: Optional[Dict[str, Any]] = None

            for i in range(20, len(data)):
                bar = self._build_bar(data, i)

                if position is None:
                    if entry_fn(bar):
                        qty = size_fn(bar, capital)
                        if qty > 0 and bar["close"] > 0:
                            cost = bar["close"] * qty
                            if cost <= capital:
                                position = {
                                    "symbol": symbol,
                                    "entry_price": bar["close"],
                                    "quantity": qty,
                                    "entry_idx": i,
                                }
                                capital -= cost
                else:
                    if exit_fn(bar):
                        exit_price = bar["close"]
                        pnl = (exit_price - position["entry_price"]) * position["quantity"]
                        capital += exit_price * position["quantity"]
                        all_trades.append({
                            "symbol": symbol,
                            "entry_price": position["entry_price"],
                            "exit_price": exit_price,
                            "quantity": position["quantity"],
                            "pnl": pnl,
                            "return_pct": (
                                (exit_price - position["entry_price"])
                                / position["entry_price"]
                            ) * 100
                            if position["entry_price"] != 0
                            else 0,
                            "bars_held": i - position["entry_idx"],
                        })
                        position = None

                # Track equity
                pos_value = 0
                if position:
                    pos_value = data[i]["close"] * position["quantity"]
                equity_curve.append(capital + pos_value)

            # Close any open position at end
            if position and len(data) > 0:
                exit_price = data[-1]["close"]
                pnl = (exit_price - position["entry_price"]) * position["quantity"]
                capital += exit_price * position["quantity"]
                all_trades.append({
                    "symbol": symbol,
                    "entry_price": position["entry_price"],
                    "exit_price": exit_price,
                    "quantity": position["quantity"],
                    "pnl": pnl,
                    "return_pct": (
                        (exit_price - position["entry_price"])
                        / position["entry_price"]
                    ) * 100
                    if position["entry_price"] != 0
                    else 0,
                    "bars_held": len(data) - 1 - position["entry_idx"],
                })

        # Compute metrics
        final_capital = capital
        total_return_pct = ((final_capital - initial_capital) / initial_capital) * 100

        winning = [t for t in all_trades if t["pnl"] > 0]
        losing = [t for t in all_trades if t["pnl"] <= 0]
        win_rate = (len(winning) / len(all_trades) * 100) if all_trades else 0
        avg_return = statistics.mean([t["return_pct"] for t in all_trades]) if all_trades else 0

        # Max drawdown
        max_dd = 0.0
        peak = equity_curve[0] if equity_curve else initial_capital
        for eq in equity_curve:
            if eq > peak:
                peak = eq
            dd = (peak - eq) / peak if peak > 0 else 0
            if dd > max_dd:
                max_dd = dd

        # Sharpe & Sortino (annualized)
        daily_returns = []
        for i in range(1, len(equity_curve)):
            if equity_curve[i - 1] > 0:
                daily_returns.append(
                    (equity_curve[i] - equity_curve[i - 1]) / equity_curve[i - 1]
                )

        if len(daily_returns) > 1:
            mean_ret = statistics.mean(daily_returns)
            std_ret = statistics.stdev(daily_returns)
            sharpe = (mean_ret / std_ret) * (252 ** 0.5) if std_ret > 0 else 0
            downside = [r for r in daily_returns if r < 0]
            # If there aren't enough negative returns to form a real downside
            # stdev, report Sortino as 0 rather than manufacturing a 0.0001
            # denominator that produces a wildly inflated ratio (misleading
            # to research users). We intentionally do NOT fall back to the
            # overall stdev here because that would make Sortino numerically
            # identical to Sharpe.
            if len(downside) > 1:
                downside_std = statistics.stdev(downside)
                sortino = (
                    (mean_ret / downside_std) * (252 ** 0.5)
                    if downside_std > 0
                    else 0.0
                )
            else:
                sortino = 0.0
            annual_vol = std_ret * (252 ** 0.5) * 100
        else:
            sharpe = sortino = annual_vol = 0.0

        # Date range
        s_date = start_date or "auto"
        e_date = end_date or "auto"

        result = BacktestResult(
            strategy_name=name,
            symbols=symbols,
            start_date=s_date,
            end_date=e_date,
            initial_capital=initial_capital,
            final_capital=round(final_capital, 2),
            total_return_pct=round(total_return_pct, 2),
            total_trades=len(all_trades),
            winning_trades=len(winning),
            losing_trades=len(losing),
            win_rate_pct=round(win_rate, 2),
            avg_trade_return_pct=round(avg_return, 2),
            max_drawdown_pct=round(max_dd * 100, 2),
            sharpe_ratio=round(sharpe, 4),
            sortino_ratio=round(sortino, 4),
            volatility_annual_pct=round(annual_vol, 2),
            data_points_used=total_data_points,
        )

        logger.info(f"Backtest complete: {name} | Return: {total_return_pct:.2f}%")
        return result.to_dict()

    def _fetch_data(
        self, symbol: str, start_date: Optional[str], end_date: Optional[str]
    ) -> List[Dict[str, Any]]:
        """Fetch historical data via yfinance."""
        try:
            import yfinance as yf
        except ImportError as e:
            raise ImportError(
                "yfinance is required for backtesting: pip install yfinance"
            ) from e

        kwargs: Dict[str, Any] = {}
        if start_date:
            kwargs["start"] = start_date
        if end_date:
            kwargs["end"] = end_date
        if not kwargs:
            kwargs["period"] = "1y"

        ticker = yf.Ticker(symbol)
        df = ticker.history(**kwargs)

        bars = []
        for ts, row in df.iterrows():
            bars.append({
                "timestamp": str(ts),
                "open": float(row["Open"]),
                "high": float(row["High"]),
                "low": float(row["Low"]),
                "close": float(row["Close"]),
                "volume": int(row["Volume"]),
            })
        return bars

    @staticmethod
    def _build_bar(data: List[Dict], idx: int) -> Dict[str, Any]:
        """Build a data bar with computed indicators for strategy hooks."""
        bar = dict(data[idx])

        closes = [d["close"] for d in data[max(0, idx - 199): idx + 1]]

        if len(closes) >= 20:
            bar["sma_20"] = statistics.mean(closes[-20:])
        if len(closes) >= 50:
            bar["sma_50"] = statistics.mean(closes[-50:])
        if len(closes) >= 200:
            bar["sma_200"] = statistics.mean(closes[-200:])

        # RSI (14-period)
        if len(closes) >= 15:
            gains, losses = [], []
            for i in range(1, min(15, len(closes))):
                diff = closes[-i] - closes[-i - 1]
                if diff > 0:
                    gains.append(diff)
                else:
                    losses.append(abs(diff))
            avg_gain = statistics.mean(gains) if gains else 0.0001
            avg_loss = statistics.mean(losses) if losses else 0.0001
            rs = avg_gain / avg_loss if avg_loss != 0 else 100
            bar["rsi_14"] = 100 - (100 / (1 + rs))

        return bar
