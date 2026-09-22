from collections import deque
from .indicators import Mean, Smooth, RSI, ATR, Stochastic, MACD, Bollinger, HeikinAshi, Fractal, ZigZag


class Features:
    def __init__(self, config):
        self.config, self.rows = config, []
        p = config["strategies"]
        periods = {p["01"][k] for k in ("fast", "middle", "slow")}
        periods.update(p["02"]["mas"] + [p["02"]["anchor"], p["03"]["ma"], p["06"]["ma"]])
        periods.update(p[s][k] for s in ("07", "08") for k in ("fast", "slow"))
        self.mas = {n: Mean(n) for n in periods}
        self.rsis = {s: RSI(p[s]["rsi"]) for s in ("01", "06")}
        self.stochs = {s: Stochastic(*p[s]["stoch"]) for s in ("03", "04", "05", "08")}
        self.macds = {s: MACD(*p[s]["macd"]) for s in ("02", "08")}
        self.ha = HeikinAshi()
        self.bb = Bollinger(p["04"]["bb"], p["04"]["deviation"])
        self.kema, self.katr = Smooth(p["05"]["ema"]), ATR(p["05"]["atr"])
        self.fractal = Fractal(p["07"]["fractal_wing"])
        self.zigzag = ZigZag(p["05"]["zigzag_atr"], p["05"]["zigzag_depth"])
        self.donchian = deque(maxlen=p["06"]["donchian"])
        self.atr, self.atr_baseline = ATR(14), Mean(50)
        self.closes = deque(maxlen=config["regime"]["efficiency_period"]+1)

    def update(self, c):
        i = len(self.rows)
        ha = self.ha.update(c)
        row = {"candle": c, "ha": ha, "ma": {n: ma.update(c.close) for n, ma in self.mas.items()}}
        row["rsi"] = {s: obj.update(c.close) for s, obj in self.rsis.items()}
        row["stoch"] = {s: obj.update(ha if s == "04" else c) for s, obj in self.stochs.items()}
        row["macd"] = {s: obj.update(c.close) for s, obj in self.macds.items()}
        row["bb"] = self.bb.update(ha.close)
        center, atr = self.kema.update(c.close), self.katr.update(c)
        row["keltner"] = (None, None) if center is None or atr is None else (center-self.config["strategies"]["05"]["multiplier"]*atr, center+self.config["strategies"]["05"]["multiplier"]*atr)
        row["zigzag"] = self.zigzag.update(c.close, atr, i)
        row["fractal"] = self.fractal.update(c, i)
        row["donchian"] = (min(x.low for x in self.donchian), max(x.high for x in self.donchian)) if len(self.donchian) == self.donchian.maxlen else (None, None)
        self.donchian.append(c)  # exclude current candle from breakout range
        a = self.atr.update(c)
        baseline = self.atr_baseline.update(a)
        self.closes.append(c.close)
        path = sum(abs(b-a) for a, b in zip(self.closes, list(self.closes)[1:]))
        er = abs(c.close-self.closes[0])/path if path else 0.0
        r = self.config["regime"]
        row["regime"] = "HIGH_VOLATILITY" if baseline and a > r["volatility_ratio"]*baseline else "TREND" if len(self.closes) == self.closes.maxlen and er >= r["trend_efficiency"] else "RANGE"
        row["efficiency"] = er
        self.rows.append(row)
        return row
