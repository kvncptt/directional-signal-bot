from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from math import isfinite


def timestamp(value: str) -> str:
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        raise ValueError("timestamps must include a timezone")
    return dt.astimezone(timezone.utc).isoformat()


@dataclass(frozen=True)
class Candle:
    symbol: str
    timeframe: str
    timestamp: str  # candle CLOSE time, not open time
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0
    complete: bool = True

    def __post_init__(self):
        object.__setattr__(self, "timestamp", timestamp(self.timestamp))
        if not self.symbol or not self.timeframe:
            raise ValueError("symbol and timeframe are required")
        if not isinstance(self.complete, bool):
            raise ValueError("complete must be boolean")
        if not all(isfinite(v) for v in (self.open, self.high, self.low, self.close, self.volume)):
            raise ValueError("OHLCV must be finite")
        if self.low <= 0 or self.low > min(self.open, self.close) or self.high < max(self.open, self.close) or self.volume < 0:
            raise ValueError("invalid OHLCV bounds")


@dataclass(frozen=True)
class Vote:
    strategy: str
    direction: str  # UP / DOWN / NEUTRAL
    reason: str


@dataclass(frozen=True)
class Signal:
    symbol: str
    timeframe: str
    timestamp: str
    entry: float
    horizon: int
    direction: str
    confidence: float  # agreement score; not a calibrated probability
    regime: str
    strategy_votes: tuple[Vote, ...]
    weights: dict[str, float]
    confidence_kind: str = "weighted_agreement"

    def to_dict(self):
        return asdict(self)


def label(direction: str, entry: float, future_close: float) -> str:
    if direction not in ("UP", "DOWN"):
        raise ValueError("direction must be UP or DOWN")
    if future_close == entry:
        return "TIE"
    return "WIN" if (future_close > entry) == (direction == "UP") else "LOSS"
