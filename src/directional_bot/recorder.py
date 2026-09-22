"""Measure strategy 01 using the existing local live feed; no credentials needed.

The source monitor already persists each candle. This process follows that run,
rebuilds causal indicators and persists separate, all-signal 1m/3m measurements.
"""
import csv
import argparse
import json
import sqlite3
import time
from pathlib import Path
from .models import Candle
from .live import strategy01_config
from .engine import Engine
from .storage import Store


def export_measurements(store, run_id, path):
    started=store.db.execute("SELECT created FROM runs WHERE id=?",(run_id,)).fetchone()[0]
    rows=store.db.execute("""SELECT a.timestamp,a.symbol,a.direction,a.entry,
      a.future_close AS close_1m,a.outcome AS result_1m,
      b.future_close AS close_3m,b.outcome AS result_3m,a.regime
      FROM predictions a JOIN predictions b
      ON a.run_id=b.run_id AND a.symbol=b.symbol AND a.timeframe=b.timeframe
      AND a.idx=b.idx AND a.source=b.source
      WHERE a.run_id=? AND a.source='01' AND a.horizon=1 AND b.horizon=3
      ORDER BY a.timestamp""",(run_id,)).fetchall()
    path=Path(path)
    temporary=path.with_suffix('.tmp')
    with temporary.open('w',newline='') as f:
        fields=['timestamp','symbol','direction','entry','close_1m','result_1m','close_3m','result_3m','regime','collection']
        writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader()
        for row in rows:
            record=dict(row)
            record['result_1m']=record['result_1m'] or 'PENDING'
            record['result_3m']=record['result_3m'] or 'PENDING'
            record['collection']='historical_replay' if record['timestamp']<started else 'live'
            writer.writerow(record)
    temporary.replace(path)


def record(source_path, output_path, source_run=None, once=False):
    if Path(source_path).resolve()==Path(output_path).resolve():
        raise ValueError("Recorder database must differ from source database")
    source=sqlite3.connect(f"file:{Path(source_path).resolve()}?mode=ro",uri=True)
    source.row_factory=sqlite3.Row
    if source_run:
        row=source.execute("SELECT * FROM runs WHERE id=?",(source_run,)).fetchone()
    else:
        row=source.execute("SELECT * FROM runs WHERE source='OANDA practice M1 midpoint live' ORDER BY rowid DESC LIMIT 1").fetchone()
    if row is None:raise ValueError("No OANDA live source run found")
    source_run=row["id"]
    store=Store(output_path)
    cfg=strategy01_config()
    engine=Engine(cfg,store,"paper",f"Strategy01 measurements of OANDA run {source_run}")
    last_rowid=0
    try:
        print(json.dumps({"event":"recording","source_run":source_run,"run_id":engine.run_id,"horizons_minutes":[1,3],"execution_enabled":False}),flush=True)
        while True:
            rows=source.execute("SELECT rowid,payload FROM candles WHERE run_id=? AND rowid>? ORDER BY rowid LIMIT 5000",(source_run,last_rowid)).fetchall()
            for raw in rows:
                c=Candle(**json.loads(raw["payload"]))
                # Evaluate all stored candles causally after indicator warmup,
                # including source startup history, tagged by this separate run.
                signals=engine.ingest(c)
                for s in signals:
                    print(json.dumps({"event":"measurement_signal",**s.to_dict()}),flush=True)
                last_rowid=raw["rowid"]
            if rows:
                export_measurements(store,engine.run_id,Path(output_path).with_suffix(".csv"))
            status=source.execute("SELECT status FROM runs WHERE id=?",(source_run,)).fetchone()[0]
            if once or (status!="running" and not rows):break
            time.sleep(2)
        store.finish(engine.run_id)
    except KeyboardInterrupt:
        store.finish(engine.run_id,"stopped")
    except Exception:
        store.finish(engine.run_id,"failed")
        raise
    finally:
        source.close();store.close()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source-db",default="data/live-strategy01.sqlite3")
    p.add_argument("--db",default="data/strategy01-measurements.sqlite3")
    p.add_argument("--source-run")
    p.add_argument("--once",action="store_true")
    a=p.parse_args()
    record(a.source_db,a.db,a.source_run,a.once)


if __name__=="__main__":main()
