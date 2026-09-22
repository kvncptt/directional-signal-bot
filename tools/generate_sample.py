"""Deterministic synthetic candles for plumbing tests, never evidence of edge."""
import csv
import math
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

rng = random.Random(42)
path = Path(__file__).resolve().parents[1] / "data/sample.csv"
price = 1.1
with path.open("w", newline="") as f:
    writer = csv.writer(f)
    writer.writerow(["symbol","timeframe","timestamp","open","high","low","close","volume","complete"])
    for i in range(2400):
        op = price
        phase = i % 600
        drift = 0.00006 if phase < 150 else -0.00006 if phase < 300 else 0
        price += drift + 0.00018*math.sin(i/7) + rng.gauss(0,0.00012 if phase<500 else 0.0004)
        high = max(op,price)+rng.uniform(0.00001,0.00012)
        low = min(op,price)-rng.uniform(0.00001,0.00012)
        writer.writerow(["SYNTHETIC_EUR_USD","1m",(datetime(2025,1,1,tzinfo=timezone.utc)+timedelta(minutes=i+1)).isoformat(),*[f"{v:.6f}" for v in (op,high,low,price)],100,"true"])
print(path)
