"""Wilder RSI calculation with safe previews for an unfinished candle."""

from __future__ import annotations

from collections.abc import Sequence
import math


def _rsi_from_averages(average_gain: float, average_loss: float) -> float:
    if average_gain == 0 and average_loss == 0:
        return 50.0
    if average_loss == 0:
        return 100.0
    if average_gain == 0:
        return 0.0
    relative_strength = average_gain / average_loss
    return 100.0 - (100.0 / (1.0 + relative_strength))


def _validate_close(value: float) -> float:
    close = float(value)
    if not math.isfinite(close) or close < 0:
        raise ValueError("Candle close must be a finite, non-negative number")
    return close


class WilderRSI:
    """Incremental Wilder RSI. Initialize with CLOSED candle closes only.

    preview() calculates a forming-candle RSI without changing stored state.
    Call commit() exactly once when that candle closes.
    """

    def __init__(self, closes: Sequence[float], period: int = 6) -> None:
        if period < 2:
            raise ValueError("RSI period must be at least 2")
        if len(closes) < period + 1:
            raise ValueError(f"At least {period + 1} closes are required to seed RSI({period})")

        values = [_validate_close(value) for value in closes]
        changes = [current - previous for previous, current in zip(values, values[1:])]
        gains = [max(change, 0.0) for change in changes]
        losses = [max(-change, 0.0) for change in changes]

        self.period = period
        self.average_gain = sum(gains[:period]) / period
        self.average_loss = sum(losses[:period]) / period
        for gain, loss in zip(gains[period:], losses[period:]):
            self.average_gain = ((self.average_gain * (period - 1)) + gain) / period
            self.average_loss = ((self.average_loss * (period - 1)) + loss) / period
        self.last_close = values[-1]

    @property
    def value(self) -> float:
        """RSI of the most recently committed closed candle."""
        return _rsi_from_averages(self.average_gain, self.average_loss)

    def preview(self, forming_close: float) -> float:
        """Calculate RSI for a forming candle without mutating Wilder state."""
        close = _validate_close(forming_close)
        change = close - self.last_close
        gain = max(change, 0.0)
        loss = max(-change, 0.0)
        candidate_gain = ((self.average_gain * (self.period - 1)) + gain) / self.period
        candidate_loss = ((self.average_loss * (self.period - 1)) + loss) / self.period
        return _rsi_from_averages(candidate_gain, candidate_loss)

    def commit(self, closed_close: float) -> float:
        """Commit one newly closed candle and return the resulting RSI."""
        close = _validate_close(closed_close)
        change = close - self.last_close
        gain = max(change, 0.0)
        loss = max(-change, 0.0)
        self.average_gain = ((self.average_gain * (self.period - 1)) + gain) / self.period
        self.average_loss = ((self.average_loss * (self.period - 1)) + loss) / self.period
        self.last_close = close
        return self.value
