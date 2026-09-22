from .models import Signal


def combine(candle, votes, regime, horizon, config):
    weights = {v.strategy: config["weights"][v.strategy]*config["regime_multipliers"][regime][v.strategy] for v in votes}
    active = [v for v in votes if v.direction != "NEUTRAL" and weights[v.strategy] > 0]
    if len(active) < config["min_active_votes"]: return None
    if regime == "HIGH_VOLATILITY" and config["skip_high_volatility"]: return None
    totals = {d: sum(weights[v.strategy] for v in active if v.direction == d) for d in ("UP", "DOWN")}
    if totals["UP"] == totals["DOWN"]: return None
    direction = max(totals, key=totals.get)
    confidence = totals[direction]/sum(totals.values())
    threshold = config["horizon_thresholds"].get(str(horizon), config["confidence_threshold"])
    if confidence < threshold: return None
    return Signal(candle.symbol, candle.timeframe, candle.timestamp, candle.close, horizon, direction, confidence, regime, votes, weights)
