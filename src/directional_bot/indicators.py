"""Causal indicators. Warmup is None; no centered rolling windows/backfill."""
from collections import deque
from math import sqrt


class Mean:
    def __init__(self, period): self.values = deque(maxlen=period)
    def update(self, x):
        if x is None: return None
        self.values.append(x)
        return sum(self.values) / len(self.values) if len(self.values) == self.values.maxlen else None


class Smooth:
    def __init__(self, period, wilder=False):
        self.seed = Mean(period)
        self.alpha = 1 / period if wilder else 2 / (period + 1)
        self.value = None
    def update(self, x):
        if x is None: return None
        if self.value is None: self.value = self.seed.update(x)
        else: self.value += self.alpha * (x - self.value)
        return self.value


class RSI:
    def __init__(self, period):
        self.gain, self.loss, self.previous = Smooth(period, True), Smooth(period, True), None
    def update(self, x):
        old, self.previous = self.previous, x
        if old is None: return None
        g, l = self.gain.update(max(x-old, 0)), self.loss.update(max(old-x, 0))
        if g is None: return None
        if g == l == 0: return 50.0
        return 100.0 if l == 0 else 100 - 100 / (1 + g/l)


class ATR:
    def __init__(self, period): self.mean, self.previous = Smooth(period, True), None
    def update(self, c):
        tr = c.high-c.low if self.previous is None else max(c.high-c.low, abs(c.high-self.previous), abs(c.low-self.previous))
        self.previous = c.close
        return self.mean.update(tr)


class Stochastic:
    def __init__(self, n, k, d): self.window, self.k, self.d = deque(maxlen=n), Mean(k), Mean(d)
    def update(self, c):
        self.window.append(c)
        if len(self.window) < self.window.maxlen: return None, None
        lo, hi = min(x.low for x in self.window), max(x.high for x in self.window)
        k = self.k.update(50.0 if hi == lo else 100*(c.close-lo)/(hi-lo))
        return k, self.d.update(k)


class MACD:
    def __init__(self, fast, slow, signal): self.fast, self.slow, self.signal = Smooth(fast), Smooth(slow), Smooth(signal)
    def update(self, x):
        f, s = self.fast.update(x), self.slow.update(x)
        m = None if f is None or s is None else f-s
        sig = self.signal.update(m)
        return m, sig, None if sig is None else m-sig


class Bollinger:
    def __init__(self, period, deviation): self.window, self.deviation = deque(maxlen=period), deviation
    def update(self, x):
        self.window.append(x)
        if len(self.window) < self.window.maxlen: return None, None, None
        m = sum(self.window)/len(self.window)
        sd = sqrt(sum((v-m)**2 for v in self.window)/len(self.window))
        return m-self.deviation*sd, m, m+self.deviation*sd


class HeikinAshi:
    def __init__(self): self.previous = None
    def update(self, c):
        from .models import Candle
        close = (c.open+c.high+c.low+c.close)/4
        op = (c.open+c.close)/2 if self.previous is None else (self.previous.open+self.previous.close)/2
        self.previous = Candle(c.symbol, c.timeframe, c.timestamp, op, max(c.high, op, close), min(c.low, op, close), close, c.volume)
        return self.previous


class Fractal:
    """Strict, symmetric pivot becomes visible only after wing right bars close."""
    def __init__(self, wing): self.wing, self.window = wing, deque(maxlen=2*wing+1)
    def update(self, c, index):
        self.window.append(c)
        if len(self.window) < self.window.maxlen: return None
        w = list(self.window)
        p = w[self.wing]
        others = w[:self.wing]+w[self.wing+1:]
        low = all(p.low < x.low for x in others)
        high = all(p.high > x.high for x in others)
        # Outside bars marking both extremes are ambiguous: abstain.
        if low == high: return None
        return {"direction": "UP" if low else "DOWN", "pivot_index": index-self.wing, "confirmed_index": index}


class ZigZag:
    """Close-based directional-change detector; never exposes provisional pivots.

    Confirm after a reversal of ATR*multiple and depth bars after the candidate.
    The detector emits at confirmation, never at the historical candidate index.
    """
    def __init__(self, multiple, depth):
        self.multiple, self.depth = multiple, depth
        self.side, self.extreme, self.index = 0, None, None
    def update(self, close, atr, index):
        if atr is None or atr <= 0: return None
        if self.extreme is None:
            self.extreme, self.index = close, index
            return None
        delta = close-self.extreme
        if self.side == 0:
            if abs(delta) >= self.multiple*atr:
                self.side = 1 if delta > 0 else -1
                self.extreme, self.index = close, index
            return None
        if delta*self.side >= 0:
            self.extreme, self.index = close, index
            return None
        if abs(delta) < self.multiple*atr or index-self.index < self.depth: return None
        event = {"direction": "DOWN" if self.side == 1 else "UP", "pivot_index": self.index, "confirmed_index": index}
        self.side *= -1
        self.extreme, self.index = close, index
        return event
