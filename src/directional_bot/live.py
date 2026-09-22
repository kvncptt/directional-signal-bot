"""Closed-candle live monitor with startup warmup and stale-signal suppression."""
import json
import time
from datetime import datetime, timezone
from .config import load
from .engine import Engine
from .storage import Store
from .oanda import OandaData


def strategy01_config(path=None):
    cfg=load(path)
    cfg["enabled_strategies"]=["01"]
    cfg["min_active_votes"]=1
    cfg["horizons"]=[1,3]
    cfg["horizon_basis"]="minutes"
    cfg["skip_high_volatility"]=False
    cfg["confidence_threshold"]=0.5
    cfg["horizon_thresholds"]={k:v for k,v in cfg["horizon_thresholds"].items() if k in ("1","3")}
    return cfg


def monitor(engine, provider, polls=0, interval=5, emit=print, sleep=time.sleep, now=None):
    now=now or (lambda:datetime.now(timezone.utc))
    def event(kind, **values):emit(json.dumps({"event":kind,**values}),flush=True)
    initial=provider.fetch(count=max(300,engine.config["warmup"]+1))
    if not initial: raise ValueError("No complete candles returned for startup warmup")
    if len(initial)<engine.config["warmup"]: raise ValueError("Insufficient completed candles for warmup")
    for c in initial: engine.ingest(c,predict=False)
    last=initial[-1]
    event("ready",run_id=engine.run_id,symbol=last.symbol,timeframe="1m",strategy="01",last_close_time=last.timestamp,last_close=last.close,execution_enabled=False)
    n=0
    while polls==0 or n<polls:
        fresh=provider.fetch(count=5000,after_close=last.timestamp)
        accepted=0
        for c in fresh:
            if c.timestamp<last.timestamp: continue
            if c.timestamp==last.timestamp:
                engine.ingest(c,predict=False)  # validate exact latest replay
                continue
            age=(now()-datetime.fromisoformat(c.timestamp)).total_seconds()
            if age<0: raise ValueError("Provider marked a future candle complete")
            timely=age<=90
            signals=engine.ingest(c,predict=timely)
            last=c;accepted+=1
            f=engine.streams[(c.symbol,c.timeframe)].rows[-1]
            p=engine.config["strategies"]["01"]
            event("candle",timestamp=c.timestamp,close=c.close,stale=not timely,regime=f["regime"],sma6=f["ma"][p["fast"]],sma14=f["ma"][p["middle"]],sma50=f["ma"][p["slow"]],rsi5=f["rsi"]["01"],signals=len(signals))
            for signal in signals:
                event("signal",**signal.to_dict())
        event("poll",new_candles=accepted,last_close_time=last.timestamp,age_seconds=max(0,(now()-datetime.fromisoformat(last.timestamp)).total_seconds()))
        n+=1
        if polls==0 or n<polls:sleep(interval)


def run_live(args):
    if args.polls<0 or not 1<=args.interval<=60:raise ValueError("polls must be >=0 and interval 1..60 seconds")
    cfg=strategy01_config(args.config)
    if cfg["warmup"]>=5000:raise ValueError("live warmup must be below 5000")
    provider=OandaData(args.symbol)
    store=Store(args.db)
    engine=Engine(cfg,store,"paper","OANDA practice M1 midpoint live")
    try:
        monitor(engine,provider,args.polls,args.interval)
        store.finish(engine.run_id)
    except KeyboardInterrupt:
        store.finish(engine.run_id,"stopped")
    except Exception:
        store.finish(engine.run_id,"failed")
        raise
    finally:store.close()
    return 0
