import json
import math
from copy import deepcopy
from pathlib import Path

IDS = tuple(f"{i:02d}" for i in range(1, 9))
DEFAULT = {
    "execution_enabled": False,
    "enabled_strategies": list(IDS),
    "symbol_strategies": {},
    "horizons": [1, 2, 3, 5],
    "horizon_basis": "candles",
    "warmup": 120,
    "min_active_votes": 2,
    "confidence_threshold": 0.7,
    "horizon_thresholds": {},
    "weights": {s: 1.0 for s in IDS},
    "regime_multipliers": {
        "TREND": dict(zip(IDS, [1.4, 1.35, 1.1, 0.5, 0.5, 1.3, 0.4, 1.0])),
        "RANGE": dict(zip(IDS, [0.55, 0.55, 1.0, 1.35, 1.25, 0.55, 1.25, 1.15])),
        "HIGH_VOLATILITY": {s: 0.5 for s in IDS},
    },
    "skip_high_volatility": True,
    "regime": {"efficiency_period": 20, "trend_efficiency": 0.35, "volatility_ratio": 1.8},
    "strategies": {
        "01": {"fast": 6, "middle": 14, "slow": 50, "rsi": 5, "upper": 70, "lower": 30},
        "02": {"mas": [5, 9, 13, 14], "anchor": 50, "macd": [12, 26, 9], "freshness": 5, "hist_bars": 2},
        "03": {"ma": 50, "stoch": [14, 1, 4], "upper": 80, "lower": 15},
        "04": {"bb": 20, "deviation": 2.0, "stoch": [7, 3, 3], "upper": 82, "lower": 22},
        "05": {"ema": 16, "atr": 8, "multiplier": 2.0, "stoch": [13, 3, 3], "upper": 80, "lower": 20, "zigzag_atr": 1.0, "zigzag_depth": 6, "confirmation_window": 3},
        "06": {"donchian": 31, "ma": 45, "rsi": 7, "upper": 70, "lower": 30},
        "07": {"fast": 6, "slow": 14, "fractal_wing": 2},
        "08": {"fast": 6, "slow": 13, "macd": [13, 27, 8], "stoch": [26, 6, 6], "freshness": 3},
    },
}


def load(path=None):
    cfg = deepcopy(DEFAULT)
    def merge(dst, src):
        for key, value in src.items():
            if key not in dst:
                raise ValueError(f"unknown config key: {key}")
            if isinstance(dst[key], dict) and key not in ("horizon_thresholds", "symbol_strategies"):
                if not isinstance(value, dict):
                    raise ValueError(f"{key} must be an object")
                merge(dst[key], value)
            else:
                dst[key] = value
    if path:
        merge(cfg, json.loads(Path(path).read_text()))
    validate(cfg)
    return cfg


def validate(c):
    if c["execution_enabled"] is not False:
        raise ValueError("Live execution is unsupported; execution_enabled must be false")
    if c["horizon_basis"] not in ("candles", "minutes"):
        raise ValueError("horizon_basis must be candles or minutes")
    enabled = c["enabled_strategies"]
    if not isinstance(enabled, list) or not enabled or any(s not in IDS for s in enabled) or len(set(enabled)) != len(enabled):
        raise ValueError("enabled_strategies must contain unique strategy IDs 01..08")
    if not isinstance(c["symbol_strategies"], dict) or any(not isinstance(v, list) or not v or any(s not in IDS for s in v) for v in c["symbol_strategies"].values()):
        raise ValueError("symbol_strategies must map pairs to strategy ID lists")
    def integer(v, name):
        if type(v) is not int or v < 1:
            raise ValueError(f"{name} must be a positive integer")
    def number(v, name, low=0, high=float("inf")):
        if type(v) not in (float, int) or not math.isfinite(v) or not low <= v <= high:
            raise ValueError(f"invalid {name}")
    if not isinstance(c["horizons"], list) or not c["horizons"]:
        raise ValueError("horizons must be a nonempty list")
    for h in c["horizons"]: integer(h, "horizon")
    if len(set(c["horizons"])) != len(c["horizons"]):
        raise ValueError("duplicate horizons")
    integer(c["warmup"], "warmup")
    integer(c["min_active_votes"], "min_active_votes")
    if c["min_active_votes"] > 8: raise ValueError("min_active_votes exceeds 8")
    number(c["confidence_threshold"], "confidence_threshold", 0.5, 1)
    for h, t in c["horizon_thresholds"].items():
        if h not in {str(x) for x in c["horizons"]}: raise ValueError("unknown threshold horizon")
        number(t, "horizon threshold", 0.5, 1)
    for weights in [c["weights"], *c["regime_multipliers"].values()]:
        for w in weights.values(): number(w, "weight")
    if not any(c["weights"].values()): raise ValueError("at least one weight must be positive")
    if type(c["skip_high_volatility"]) is not bool: raise ValueError("skip_high_volatility must be boolean")
    integer(c["regime"]["efficiency_period"], "efficiency_period")
    number(c["regime"]["trend_efficiency"], "trend_efficiency", 0, 1)
    number(c["regime"]["volatility_ratio"], "volatility_ratio", 1)
    for sid, params in c["strategies"].items():
        for key, val in params.items():
            if isinstance(val, list):
                for v in val: integer(v, key)
            elif key in {"deviation", "multiplier", "zigzag_atr"}:
                number(val, key, 0.000001)
            else: integer(val, key)
        if "upper" in params and not 0 < params["lower"] < params["upper"] < 100:
            raise ValueError("invalid oscillator bands")
        for key in ("stoch", "macd"):
            if key in params and len(params[key]) != 3: raise ValueError(f"{key} needs three periods")
        if "macd" in params and params["macd"][0] >= params["macd"][1]: raise ValueError("MACD fast must be below slow")
    if len(c["strategies"]["02"]["mas"]) < 2: raise ValueError("MA cluster needs at least two periods")
