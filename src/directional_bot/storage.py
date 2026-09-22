import json
import sqlite3
from dataclasses import asdict
from pathlib import Path
from uuid import uuid4
from datetime import datetime, timezone
from .models import label


class Store:
    def __init__(self, path):
        if str(path) != ":memory:": Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.executescript('''
        CREATE TABLE IF NOT EXISTS runs (
          id TEXT PRIMARY KEY, created TEXT NOT NULL, mode TEXT NOT NULL,
          config TEXT NOT NULL, source TEXT NOT NULL, status TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS candles (
          run_id TEXT NOT NULL REFERENCES runs(id), symbol TEXT NOT NULL,
          timeframe TEXT NOT NULL, idx INTEGER NOT NULL, timestamp TEXT NOT NULL,
          payload TEXT NOT NULL, PRIMARY KEY(run_id,symbol,timeframe,idx),
          UNIQUE(run_id,symbol,timeframe,timestamp));
        CREATE TABLE IF NOT EXISTS predictions (
          id INTEGER PRIMARY KEY, run_id TEXT NOT NULL REFERENCES runs(id),
          symbol TEXT NOT NULL, timeframe TEXT NOT NULL, idx INTEGER NOT NULL,
          timestamp TEXT NOT NULL, source TEXT NOT NULL, horizon INTEGER NOT NULL,
          direction TEXT NOT NULL, entry REAL NOT NULL, regime TEXT NOT NULL,
          confidence REAL, payload TEXT NOT NULL,
          outcome TEXT, future_close REAL, resolved_timestamp TEXT,
          UNIQUE(run_id,symbol,timeframe,idx,source,horizon));
        CREATE INDEX IF NOT EXISTS pending ON predictions(run_id,symbol,timeframe,outcome,idx);
        ''')

    def create_run(self, config, mode, source):
        rid = uuid4().hex
        with self.db:
            self.db.execute("INSERT INTO runs VALUES(?,?,?,?,?,?)", (rid,datetime.now(timezone.utc).isoformat(),mode,json.dumps(config,sort_keys=True),source,"running"))
        return rid

    def record_candle(self, run, c, index):
        self.db.execute("INSERT INTO candles VALUES(?,?,?,?,?,?)", (run,c.symbol,c.timeframe,index,c.timestamp,json.dumps(asdict(c))))

    def prediction(self, run, c, index, source, horizon, direction, regime, payload, confidence=None):
        self.db.execute('''INSERT INTO predictions
          (run_id,symbol,timeframe,idx,timestamp,source,horizon,direction,entry,regime,confidence,payload)
          VALUES(?,?,?,?,?,?,?,?,?,?,?,?)''',
          (run,c.symbol,c.timeframe,index,c.timestamp,source,horizon,direction,c.close,regime,confidence,json.dumps(payload)))

    def resolve(self, run, c, index, horizon_basis="candles"):
        rows = self.db.execute("SELECT id,direction,entry FROM predictions WHERE run_id=? AND symbol=? AND timeframe=? AND outcome IS NULL AND idx+horizon=?", (run,c.symbol,c.timeframe,index)).fetchall()
        if horizon_basis == "minutes":
            rows = self.db.execute("SELECT id,direction,entry FROM predictions WHERE run_id=? AND symbol=? AND timeframe=? AND outcome IS NULL AND datetime(timestamp, '+' || horizon || ' minutes')=datetime(?)", (run,c.symbol,c.timeframe,c.timestamp)).fetchall()
        for row in rows:
            self.db.execute("UPDATE predictions SET outcome=?,future_close=?,resolved_timestamp=? WHERE id=?", (label(row["direction"],row["entry"],c.close),c.close,c.timestamp,row["id"]))

    def finish(self, run, status="completed"):
        with self.db: self.db.execute("UPDATE runs SET status=? WHERE id=?", (status,run))

    def latest_run(self):
        row = self.db.execute("SELECT id FROM runs ORDER BY rowid DESC LIMIT 1").fetchone()
        if row is None: raise ValueError("database has no runs")
        return row[0]

    def statistics(self, run):
        groups = self.db.execute('''SELECT source,horizon,regime,COUNT(*) total,
          SUM(outcome='WIN') wins,SUM(outcome='LOSS') losses,SUM(outcome='TIE') ties,
          SUM(outcome IS NULL) pending FROM predictions WHERE run_id=?
          GROUP BY source,horizon,regime ORDER BY source,horizon,regime''', (run,)).fetchall()
        result = []
        for row in groups:
            d = dict(row)
            for key in ("wins","losses","ties"): d[key] = d[key] or 0
            settled = d["wins"]+d["losses"]+d["ties"]
            decisive = d["wins"]+d["losses"]
            d["win_rate"] = d["wins"]/settled if settled else None
            d["decisive_win_rate"] = d["wins"]/decisive if decisive else None
            result.append(d)
        return result

    def signals(self, run, limit=20):
        return [dict(r) for r in self.db.execute("SELECT payload,outcome,future_close FROM predictions WHERE run_id=? AND source='ensemble' ORDER BY id DESC LIMIT ?", (run,limit))]

    def close(self): self.db.close()
