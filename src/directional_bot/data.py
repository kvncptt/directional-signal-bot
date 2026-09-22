"""Read-only market-data adapters. All timestamps represent candle close times."""
import csv
import json
from pathlib import Path
from typing import Iterable, Protocol
from .models import Candle


class MarketData(Protocol):
    def candles(self) -> Iterable[Candle]: ...


def parse(row):
    fields = {k: row[k] for k in ("symbol", "timeframe", "timestamp")}
    for k in ("open", "high", "low", "close", "volume"):
        fields[k] = float(row.get(k, 0))
    complete = row.get("complete", True)
    if isinstance(complete, str):
        if complete.lower() not in ("true", "false", "1", "0"):
            raise ValueError("complete must be true/false/1/0")
        complete = complete.lower() in ("true", "1")
    return Candle(**fields, complete=complete)


class CSVData:
    def __init__(self, path): self.path = Path(path)
    def candles(self):
        with self.path.open(newline="") as f:
            for line, row in enumerate(csv.DictReader(f), 2):
                try: yield parse(row)
                except (KeyError, ValueError, TypeError) as e:
                    raise ValueError(f"{self.path}:{line}: {e}") from e


class JSONLData:
    """One complete OHLCV object per line; supports stdin and exported feeds."""
    def __init__(self, stream): self.stream = stream
    def candles(self):
        for line, raw in enumerate(self.stream, 1):
            if raw.strip():
                try: yield parse(json.loads(raw))
                except (KeyError, ValueError, TypeError) as e:
                    raise ValueError(f"JSONL line {line}: {e}") from e
