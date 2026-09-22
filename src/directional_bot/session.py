"""Eight-pair session with persistent status and an enforced entry deadline."""
import argparse
import json
import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from .config import load
from .engine import Engine
from .oanda import OandaData
from .storage import Store

PAIRS={"01":"EUR_USD","02":"GBP_USD","03":"AUD_USD","04":"NZD_USD","05":"USD_JPY","06":"USD_CHF","07":"USD_CAD","08":"USD_SGD"}
NAMES={"01":"MA Stack + RSI","02":"Multi MA + MACD","03":"MA + Stochastic","04":"Bollinger + Heikin Ashi","05":"Keltner + Stoch + ZigZag","06":"Donchian Breakout","07":"Fractal Reversal","08":"Oscillator Confluence"}

# Feed IDs stay stable for saved history; strategy assignment is independent.
ASSIGNMENTS={"01":"01","02":"02","03":"03","04":"01","05":"02","06":"03","07":"08","08":"08"}


def strategy_for(config, feed):
    return config.get('symbol_strategies',{}).get(PAIRS[feed],[feed])[0]


def apply_assignments(engine, wall):
    mapping={pair:[ASSIGNMENTS[feed]] for feed,pair in PAIRS.items()}
    if engine.config.get('symbol_strategies')==mapping:return
    engine.config.setdefault('assignment_history',[]).append({
        'effective_at':wall.isoformat(),'previous':engine.config.get('symbol_strategies',{}),'current':mapping})
    engine.config['symbol_strategies']=mapping
    engine.config['enabled_strategies']=['01','02','03','08']
    with engine.store.db:
        engine.store.db.execute('UPDATE runs SET config=? WHERE id=?',(json.dumps(engine.config),engine.run_id))


def now_utc():return datetime.now(timezone.utc)


def deadline_today():
    return datetime.now(ZoneInfo('America/Detroit')).replace(hour=17,minute=0,second=0,microsecond=0).astimezone(timezone.utc)


def weekday_open(wall):
    return wall.astimezone(ZoneInfo('America/Detroit')).weekday()<5


def next_weekend(wall):
    local=wall.astimezone(ZoneInfo('America/Detroit'))
    days=(5-local.weekday())%7
    if days==0:days=7
    return (local+timedelta(days=days)).replace(hour=0,minute=0,second=0,microsecond=0).astimezone(timezone.utc)


def weekend_settling(wall):
    local=wall.astimezone(ZoneInfo('America/Detroit'))
    return local.weekday()==5 and local.hour==0 and local.minute<4


def setup(store):
    store.db.execute('PRAGMA journal_mode=WAL')
    store.db.executescript('''
    CREATE TABLE IF NOT EXISTS sessions(run_id TEXT PRIMARY KEY REFERENCES runs(id), deadline TEXT NOT NULL, heartbeat TEXT NOT NULL, phase TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS feeds(run_id TEXT NOT NULL, strategy TEXT NOT NULL, symbol TEXT NOT NULL, state TEXT NOT NULL, last_close TEXT, price REAL, message TEXT, PRIMARY KEY(run_id,strategy));
    ''')
    columns={r[1] for r in store.db.execute('PRAGMA table_info(sessions)')}
    if 'schedule' not in columns:store.db.execute("ALTER TABLE sessions ADD COLUMN schedule TEXT NOT NULL DEFAULT 'deadline'")
    store.db.commit()


def session_config():
    cfg=load()
    cfg.update(horizons=[1,3],horizon_basis='minutes',min_active_votes=1,skip_high_volatility=False,confidence_threshold=0.5)
    cfg['symbol_strategies']={pair:[ASSIGNMENTS[feed]] for feed,pair in PAIRS.items()}
    cfg['enabled_strategies']=['01','02','03','08']
    return cfg


def eligible(c, wall, deadline):
    closed=datetime.fromisoformat(c.timestamp)
    return wall<deadline and closed<deadline and 0 <= (wall-closed).total_seconds() <=90


def collect(db_path, deadline, interval=5, client_factory=OandaData, clock=now_utc, sleep=time.sleep, max_cycles=None, start_guard=False, weekdays=False, resume=False):
    if deadline.tzinfo is None:raise ValueError('Deadline must include timezone')
    if not weekdays and clock()>=deadline:raise ValueError('The session deadline has already passed')
    # Validate environment before creating a session.
    clients={sid:client_factory(pair) for sid,pair in PAIRS.items()}
    store=Store(db_path);setup(store)
    active=store.db.execute("SELECT heartbeat FROM sessions WHERE phase IN ('collecting','settling','weekend_pause') ORDER BY rowid DESC LIMIT 1").fetchone()
    if active and (clock()-datetime.fromisoformat(active[0])).total_seconds()<120:
        store.close();raise ValueError('A collector is already active for this database')
    if resume:
        previous=store.db.execute('SELECT run_id FROM sessions ORDER BY rowid DESC LIMIT 1').fetchone()
        if previous is None:raise ValueError('No session available to resume')
        engine=Engine.restore(store,previous['run_id'])
    else:
        engine=Engine(session_config(),store,'paper','Eight strategy OANDA demo session')
    apply_assignments(engine,clock())
    run=engine.run_id
    if weekdays:deadline=next_weekend(clock())
    with store.db:
        store.db.execute('INSERT OR REPLACE INTO sessions(run_id,deadline,heartbeat,phase,schedule) VALUES(?,?,?,?,?)',(run,deadline.isoformat(),clock().isoformat(),'collecting','weekdays' if weekdays else 'deadline'))
        store.db.execute("UPDATE runs SET status='running' WHERE id=?",(run,))
        for sid,pair in PAIRS.items():store.db.execute('INSERT OR IGNORE INTO feeds VALUES(?,?,?,?,?,?,?)',(run,sid,pair,'connecting',None,None,''))
    print(json.dumps({'session':run,'stop_entries':deadline.isoformat(),'pairs':PAIRS}),flush=True)
    if start_guard:
        import subprocess,sys
        from pathlib import Path
        subprocess.Popen([sys.executable,'-m','directional_bot.trend_guard','--db',str(Path(db_path).resolve())],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)
    last={sid:engine.last[(pair,'1m')] for sid,pair in PAIRS.items() if (pair,'1m') in engine.last};cycles=0
    try:
        with ThreadPoolExecutor(max_workers=8) as pool:
            while weekdays or clock()<deadline+timedelta(minutes=3,seconds=30):
                if weekdays and not weekday_open(clock()) and not weekend_settling(clock()):
                    with store.db:
                        store.db.execute("UPDATE sessions SET phase='weekend_pause',heartbeat=? WHERE run_id=?",(clock().isoformat(),run))
                        store.db.execute("UPDATE feeds SET state='paused',message='Weekend pause; resumes Monday 00:00 Detroit' WHERE run_id=?",(run,))
                    cycles+=1
                    if max_cycles and cycles>=max_cycles:break
                    sleep(30)
                    continue
                if weekdays and weekday_open(clock()):deadline=next_weekend(clock())
                phase='collecting' if (weekday_open(clock()) if weekdays else clock()<deadline) else 'settling'
                with store.db:store.db.execute('UPDATE sessions SET phase=?,heartbeat=? WHERE run_id=?',(phase,clock().isoformat(),run))
                with store.db:store.db.execute('UPDATE sessions SET deadline=? WHERE run_id=?',(deadline.isoformat(),run))
                futures={pool.submit(client.fetch,count=300 if sid not in last else 5000,after_close=last[sid].timestamp if sid in last else None):sid for sid,client in clients.items()}
                for future in as_completed(futures):
                    sid=futures[future];pair=PAIRS[sid]
                    try:
                        candles=future.result()
                    except Exception as exc:
                        # Adapter exceptions are sanitized; do not serialize request objects.
                        from .oanda import MarketDataError
                        message=str(exc) if isinstance(exc,(MarketDataError,ValueError)) else 'Candle request failed'
                        with store.db:store.db.execute('UPDATE feeds SET state=?,message=? WHERE run_id=? AND strategy=?',('error',message,run,sid))
                        continue
                    warming=sid not in last
                    if warming and len(candles)<engine.config['warmup']:
                        with store.db:store.db.execute('UPDATE feeds SET state=?,message=? WHERE run_id=? AND strategy=?',('warming','Waiting for sufficient candle history',run,sid))
                        continue
                    for c in candles:
                        if sid in last and c.timestamp<last[sid].timestamp:continue
                        engine.ingest(c,predict=not warming and eligible(c,clock(),deadline) and (not weekdays or (weekday_open(clock()) and weekday_open(datetime.fromisoformat(c.timestamp)))))
                        last[sid]=c
                    c=last.get(sid)
                    if c:
                        age=(clock()-datetime.fromisoformat(c.timestamp)).total_seconds()
                        with store.db:store.db.execute('UPDATE feeds SET state=?,last_close=?,price=?,message=? WHERE run_id=? AND strategy=?',('live' if age<=90 else 'stale',c.timestamp,c.close,'' if age<=90 else 'No recent completed candle',run,sid))
                cycles+=1
                if max_cycles and cycles>=max_cycles:break
                remaining=(deadline+timedelta(minutes=3,seconds=30)-clock()).total_seconds()
                if weekdays:sleep(interval)
                elif remaining>0:sleep(min(interval,remaining))
        phase='completed'
        store.finish(run)
    except KeyboardInterrupt:
        phase='stopped';store.finish(run,'stopped')
    except Exception:
        phase='failed';store.finish(run,'failed')
        raise
    finally:
        with store.db:store.db.execute('UPDATE sessions SET phase=?,heartbeat=? WHERE run_id=?',(phase,clock().isoformat(),run))
        store.close()
    return run


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--db',default='data/dashboard.sqlite3')
    p.add_argument('--until',default=deadline_today().isoformat())
    p.add_argument('--weekdays',action='store_true',help='Collect Monday-Friday in Detroit time; pause weekends')
    p.add_argument('--resume',action='store_true',help='Resume the most recent stopped session without duplicating history')
    a=p.parse_args()
    try:collect(a.db,datetime.fromisoformat(a.until),start_guard=True,weekdays=a.weekdays,resume=a.resume)
    except (ValueError,sqlite3.Error) as e:raise SystemExit(str(e))


if __name__=='__main__':main()
