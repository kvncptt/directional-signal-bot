from copy import deepcopy
from dataclasses import asdict
from .config import validate
from .features import Features
from .strategies import evaluate
from .ensemble import combine
from .models import Vote


class Engine:
    """One chronological engine shared by backtest and incremental paper feeds.

    Streams are isolated by (symbol,timeframe); horizons count observed complete
    candles within that stream. No signal can see its outcome at issuance.
    """
    def __init__(self, config, store, mode="paper", source="stream"):
        validate(config)
        self.config, self.store = deepcopy(config), store
        if mode not in ("paper", "backtest"): raise ValueError("signal-only: unsupported mode")
        self.run_id = store.create_run(config, mode, source)
        self.streams, self.last = {}, {}

    @classmethod
    def restore(cls, store, run_id):
        """Rebuild indicators from saved candles without replaying predictions."""
        import json
        from .models import Candle
        row=store.db.execute('SELECT config FROM runs WHERE id=?',(run_id,)).fetchone()
        if row is None:raise ValueError('Unknown run to resume')
        obj=cls.__new__(cls)
        obj.config=json.loads(row['config']);validate(obj.config)
        obj.store=store;obj.run_id=run_id;obj.streams={};obj.last={}
        for record in store.db.execute('SELECT payload FROM candles WHERE run_id=? ORDER BY rowid',(run_id,)):
            c=Candle(**json.loads(record['payload']));key=(c.symbol,c.timeframe)
            if key not in obj.streams:obj.streams[key]=Features(obj.config)
            obj.streams[key].update(c);obj.last[key]=c
        return obj

    def ingest(self, c, *, predict=True):
        if not c.complete: return []
        key = c.symbol,c.timeframe
        old = self.last.get(key)
        if old is not None:
            if c.timestamp == old.timestamp:
                if c == old: return []  # exact latest replay is idempotent
                raise ValueError("conflicting revision of a completed candle")
            if c.timestamp < old.timestamp: raise ValueError("out-of-order candle")
        if key not in self.streams:
            self.streams[key] = Features(self.config)
        features = self.streams[key]
        row = features.update(c)
        index = len(features.rows)-1
        signals = []
        with self.store.db:
            self.store.record_candle(self.run_id,c,index)
            self.store.resolve(self.run_id,c,index,self.config["horizon_basis"])
            if predict and index+1 >= self.config["warmup"]:
                active = self.config["symbol_strategies"].get(c.symbol, self.config["enabled_strategies"])
                votes = tuple(v if v.strategy in active else Vote(v.strategy, "NEUTRAL", "disabled") for v in evaluate(features.rows,self.config))
                for h in self.config["horizons"]:
                    # Log standalone votes even when the ensemble abstains.
                    for v in votes:
                        if v.direction != "NEUTRAL":
                            self.store.prediction(self.run_id,c,index,v.strategy,h,v.direction,row["regime"],asdict(v))
                    signal = combine(c,votes,row["regime"],h,self.config)
                    if signal:
                        self.store.prediction(self.run_id,c,index,"ensemble",h,signal.direction,row["regime"],signal.to_dict(),signal.confidence)
                        signals.append(signal)
        self.last[key] = c
        return signals

    def replay(self, provider):
        try:
            for candle in provider.candles():
                yield from self.ingest(candle)
        except Exception:
            self.store.finish(self.run_id,"failed")
            raise
        else:
            self.store.finish(self.run_id)
