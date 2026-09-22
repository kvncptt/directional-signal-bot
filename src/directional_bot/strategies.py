"""Eight deterministic baseline variants; see docs/strategy-specifications.md."""
from .models import Vote


def cross(a0, b0, a1, b1, direction):
    if any(x is None for x in (a0, b0, a1, b1)): return False
    return a0 <= b0 and a1 > b1 if direction == "UP" else a0 >= b0 and a1 < b1


def recent(rows, getter, direction, window):
    for i in range(max(1, len(rows)-window), len(rows)):
        a0, b0 = getter(rows[i-1])
        a1, b1 = getter(rows[i])
        if cross(a0, b0, a1, b1, direction): return True
    return False


def evaluate(rows, config):
    if len(rows) < 2:
        return tuple(Vote(s, "NEUTRAL", "warming up") for s in config["strategies"])
    cur, prev = rows[-1], rows[-2]
    c, old = cur["candle"], prev["candle"]
    params = config["strategies"]
    votes = []
    for sid, p in params.items():
        directions = []
        for direction in ("UP", "DOWN"):
            up = direction == "UP"
            sign = 1 if up else -1
            bullish = sign*(c.close-c.open) > 0
            def ma_cross(fast, slow, window=1):
                return recent(rows, lambda r: (r["ma"][fast], r["ma"][slow]), direction, window)
            def price_cross(n):
                return cross(old.close, prev["ma"][n], c.close, cur["ma"][n], direction)
            def stoch_cross(s, window=1):
                return recent(rows, lambda r: r["stoch"][s], direction, window)
            ok = False
            if sid == "01":
                slow, slow0, rsi = cur["ma"][p["slow"]], prev["ma"][p["slow"]], cur["rsi"][sid]
                if None not in (slow, slow0, rsi):
                    anchor = c.low > slow if up else c.high < slow
                    ok = ma_cross(p["fast"], p["middle"]) and anchor and sign*(slow-slow0) > 0 and (rsi > p["upper"] if up else rsi <= p["lower"])
            elif sid == "02":
                cluster = [cur["ma"][n] for n in p["mas"]]
                anchor, anchor0 = cur["ma"][p["anchor"]], prev["ma"][p["anchor"]]
                m, s, _ = cur["macd"][sid]
                m0, s0, _ = prev["macd"][sid]
                hist = [r["macd"][sid][2] for r in rows[-p["hist_bars"]:]]
                if None not in cluster+[anchor, anchor0, m, s, m0, s0]+hist and len(hist) == p["hist_bars"]:
                    stacked = all(sign*(a-b)>0 for a,b in zip(cluster, cluster[1:]))
                    rising = all(prev["ma"][n] is not None and sign*(cur["ma"][n]-prev["ma"][n])>0 for n in p["mas"])
                    anchor_ok = c.low > anchor if up else c.high < anchor
                    ok = stacked and rising and anchor_ok and sign*(anchor-anchor0)>0 and ma_cross(p["mas"][0], p["mas"][-1], p["freshness"]) and recent(rows, lambda r: r["macd"][sid][:2], direction, p["freshness"]) and sign*(m-m0)>0 and sign*(s-s0)>0 and all(sign*h>0 for h in hist)
            elif sid == "03":
                k, d = cur["stoch"][sid]
                k0, _ = prev["stoch"][sid]
                if None not in (k,d,k0):
                    zone = k > p["lower"] if up else k0 >= p["upper"] and k < p["upper"]
                    ok = bullish and price_cross(p["ma"]) and stoch_cross(sid) and zone
            elif sid == "04":
                ha, ha0 = cur["ha"], prev["ha"]
                lo0, mid0, hi0 = prev["bb"]
                _, mid, _ = cur["bb"]
                k0, d0 = prev["stoch"][sid]
                k, d = cur["stoch"][sid]
                if None not in (lo0,mid0,hi0,mid,k0,d0,k,d):
                    touched = ha0.low <= lo0 if up else ha0.high >= hi0
                    zone = max(k0,d0) <= p["lower"] and k>p["lower"] if up else min(k0,d0,k,d) >= p["upper"]
                    ok = touched and sign*(ha0.close-ha0.open)<0 and sign*(ha.close-ha.open)>0 and stoch_cross(sid) and zone and cross(ha0.close, mid0, ha.close, mid, direction)
            elif sid == "05":
                event = cur["zigzag"]
                if event and event["direction"] == direction:
                    pivot = rows[event["pivot_index"]]
                    lo, hi = pivot["keltner"]
                    pc = pivot["candle"]
                    k0,d0 = prev["stoch"][sid]
                    k,d = cur["stoch"][sid]
                    if None not in (lo,hi,k0,d0,k,d):
                        touched = pc.low <= lo if up else pc.high >= hi
                        zone = min(k0,d0) <= p["lower"] if up else max(k0,d0) >= p["upper"]
                        ok = touched and sign*(pc.close-pc.open)<0 and bullish and stoch_cross(sid, p["confirmation_window"]) and zone and sign*(k-k0)>0 and sign*(d-d0)>0
            elif sid == "06":
                lo,hi = cur["donchian"]
                r,r0 = cur["rsi"][sid],prev["rsi"][sid]
                if None not in (lo,hi,r,r0):
                    broken = c.high>hi if up else c.low<lo
                    level = p["upper"] if up else p["lower"]
                    ok = broken and bullish and price_cross(p["ma"]) and cross(r0,level,r,level,direction)
            elif sid == "07":
                # Candle immediately AFTER confirmation, never after the hidden pivot.
                event = prev["fractal"]
                ok = bool(event and event["direction"] == direction and bullish and ma_cross(p["fast"],p["slow"]))
            elif sid == "08":
                m,s,h = cur["macd"][sid]
                m0,s0,_ = prev["macd"][sid]
                k,d = cur["stoch"][sid]
                if None not in (m,s,h,m0,s0,k,d):
                    ok = ma_cross(p["fast"],p["slow"],p["freshness"]) and recent(rows,lambda r:r["macd"][sid][:2],direction,p["freshness"]) and stoch_cross(sid,p["freshness"]) and sign*h>0 and sign*(m-m0)>0 and sign*(s-s0)>0 and sign*(k-d)>0
            if ok: directions.append(direction)
        direction = directions[0] if len(directions) == 1 else "NEUTRAL"
        votes.append(Vote(sid, direction, "baseline conditions confirmed" if direction != "NEUTRAL" else "conditions not aligned or warming up"))
    return tuple(votes)
