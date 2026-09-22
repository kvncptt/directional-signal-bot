"""Live admission layer over raw strategy observations; retains all raw outcomes."""
import argparse,json,sqlite3,time
from datetime import datetime,timezone
from .models import Candle
from . import quality
from .trend import TrendContext,decision,POLICY


def setup(db):
    db.executescript('''
    CREATE TABLE IF NOT EXISTS quality_policy(run_id TEXT PRIMARY KEY,effective_at TEXT NOT NULL,policy TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS trend_policy(run_id TEXT PRIMARY KEY,effective_at TEXT NOT NULL,policy TEXT NOT NULL,heartbeat TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS trend_decisions(run_id TEXT NOT NULL,symbol TEXT NOT NULL,strategy TEXT NOT NULL,idx INTEGER NOT NULL,approved INTEGER NOT NULL,reason TEXT NOT NULL,context TEXT NOT NULL,scope TEXT NOT NULL,PRIMARY KEY(run_id,symbol,strategy,idx));
    CREATE TABLE IF NOT EXISTS trend_state(run_id TEXT NOT NULL,symbol TEXT NOT NULL,context TEXT NOT NULL,PRIMARY KEY(run_id,symbol));
    ''');db.commit()


def process(db,run,contexts,last):
    policy=db.execute('SELECT effective_at FROM trend_policy WHERE run_id=?',(run,)).fetchone()
    quality_row=db.execute('SELECT * FROM quality_policy WHERE run_id=?',(run,)).fetchone()
    rows=db.execute('SELECT rowid,symbol,idx,payload FROM candles WHERE run_id=? AND rowid>? ORDER BY rowid',(run,last)).fetchall()
    for row in rows:
        c=Candle(**json.loads(row['payload']));ctx=contexts.setdefault(c.symbol,TrendContext()).update(c)
        trades=db.execute("SELECT source,direction FROM predictions WHERE run_id=? AND symbol=? AND idx=? AND horizon=1 AND source!='ensemble'",(run,c.symbol,row['idx'])).fetchall()
        with db:
            for trade in trades:
                admitted,reason=decision(ctx,trade['direction'])
                if quality_row and c.timestamp>=quality_row['effective_at']:
                    ctx={**ctx,'quality_version':quality.VERSION}
                    if admitted:
                        previous=db.execute('SELECT d.idx,c.timestamp FROM trend_decisions d JOIN candles c ON c.run_id=d.run_id AND c.symbol=d.symbol AND c.idx=d.idx WHERE d.run_id=? AND d.symbol=? AND d.strategy=? AND d.approved=1 AND d.idx<? ORDER BY d.idx DESC LIMIT 1',(run,c.symbol,trade['source'],row['idx'])).fetchone()
                        admitted,extra=quality.check(c,trade['source'],trade['direction'],previous['timestamp'] if previous else None)
                        reason=(reason+' '+extra) if admitted else extra
                scope='historical_review' if c.timestamp<policy['effective_at'] else 'live'
                db.execute('INSERT OR IGNORE INTO trend_decisions VALUES(?,?,?,?,?,?,?,?)',(run,c.symbol,trade['source'],row['idx'],int(admitted),reason,json.dumps(ctx),scope))
            db.execute('INSERT OR REPLACE INTO trend_state VALUES(?,?,?)',(run,c.symbol,json.dumps(ctx)))
        last=row['rowid']
    with db:db.execute('UPDATE trend_policy SET heartbeat=? WHERE run_id=?',(datetime.now(timezone.utc).isoformat(),run))
    return last


def run(path,once=False):
    db=sqlite3.connect(path,timeout=15);db.row_factory=sqlite3.Row;setup(db)
    contexts={};last=0;rid=None
    try:
        while True:
            session=db.execute('SELECT * FROM sessions ORDER BY rowid DESC LIMIT 1').fetchone()
            if not session:raise ValueError('No live session available')
            if rid!=session['run_id']:
                rid=session['run_id'];contexts={};last=0
                now=datetime.now(timezone.utc).isoformat()
                with db:db.execute('INSERT OR IGNORE INTO trend_policy VALUES(?,?,?,?)',(rid,now,json.dumps(POLICY),now))
            last=process(db,rid,contexts,last)
            if once or session['phase'] not in ('collecting','settling','weekend_pause'):break
            time.sleep(1)
    finally:db.close()


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--db',default='data/dashboard.sqlite3');p.add_argument('--once',action='store_true');a=p.parse_args();run(a.db,a.once)


if __name__=='__main__':main()
