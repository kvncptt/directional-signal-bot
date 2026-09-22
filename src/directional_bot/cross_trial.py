"""Time-bounded extra strategy observations on the existing candle feed."""
import argparse,json,sqlite3,time
from dataclasses import asdict
from datetime import datetime,timezone
from .features import Features
from .models import Candle
from .storage import Store
from .strategies import evaluate
from .trend import TrendContext,decision
from . import quality

FOCUS={"01":3,"02":3,"03":1,"08":1}

EXTRA={'01:02':('01','02'),'04:02':('04','02'),'02:01':('02','01'),'05:01':('05','01'),'03:08':('03','08'),'06:08':('06','08'),'07:03':('07','03'),'08:03':('08','03')}

def trial_for(db,run):
    if not db.execute("SELECT 1 FROM sqlite_master WHERE name='cross_trial'").fetchone():return None
    row=db.execute('SELECT * FROM cross_trial WHERE run_id=?',(run,)).fetchone()
    return dict(row) if row else None

def process(store,run,trial,streams,last,now):
    cfg=json.loads(store.db.execute('SELECT config FROM runs WHERE id=?',(run,)).fetchone()[0])
    targets={'EUR_USD':'02','NZD_USD':'02','GBP_USD':'01','USD_JPY':'01'}
    if trial.get('second_start'):targets.update(AUD_USD='08',USD_CHF='08',USD_CAD='03',USD_SGD='03')
    rows=store.db.execute('SELECT rowid,idx,payload FROM candles WHERE run_id=? AND rowid>? ORDER BY rowid',(run,last)).fetchall()
    for row in rows:
        c=Candle(**json.loads(row['payload']));last=row['rowid']
        if c.symbol not in targets:continue
        f,tr=streams.setdefault(c.symbol,(Features(cfg),TrendContext()))
        r=f.update(c);ctx=tr.update(c)
        with store.db:
            store.resolve(run,c,row['idx'],'minutes')
            start=trial.get('second_start') if targets[c.symbol] in ('03','08') else trial['start']
            if not(start<=c.timestamp<trial['end']) or not 0<=(now-datetime.fromisoformat(c.timestamp)).total_seconds()<=90:continue
            if len(f.rows)<cfg['warmup']:continue
            sid=targets[c.symbol];v=next(v for v in evaluate(f.rows,cfg) if v.strategy==sid)
            if v.direction=='NEUTRAL':continue
            for h in (1,3):
                exists=store.db.execute('SELECT 1 FROM predictions WHERE run_id=? AND symbol=? AND idx=? AND source=? AND horizon=?',(run,c.symbol,row['idx'],sid,h)).fetchone()
                if not exists:store.prediction(run,c,row['idx'],sid,h,v.direction,r['regime'],{**asdict(v),'experiment':'cross-trial','observed_at':now.isoformat()})
            ok,reason=decision(ctx,v.direction)
            qp=store.db.execute('SELECT effective_at FROM quality_policy WHERE run_id=?',(run,)).fetchone()
            if qp and c.timestamp>=qp['effective_at']:
                ctx={**ctx,'quality_version':quality.VERSION}
                if ok:
                    prev=store.db.execute('SELECT c.timestamp FROM trend_decisions d JOIN candles c ON c.run_id=d.run_id AND c.symbol=d.symbol AND c.idx=d.idx WHERE d.run_id=? AND d.symbol=? AND d.strategy=? AND d.approved=1 AND d.idx<? ORDER BY d.idx DESC LIMIT 1',(run,c.symbol,sid,row['idx'])).fetchone()
                    ok,extra=quality.check(c,sid,v.direction,prev['timestamp'] if prev else None)
                    reason=reason+' '+extra if ok else extra
            store.db.execute('INSERT OR IGNORE INTO trend_decisions VALUES(?,?,?,?,?,?,?,?)',(run,c.symbol,sid,row['idx'],int(ok),reason,json.dumps(ctx),'live'))
    with store.db:store.db.execute('UPDATE cross_trial SET heartbeat=? WHERE run_id=?',(now.isoformat(),run))
    return last

def main():
    p=argparse.ArgumentParser();p.add_argument('--db',required=True);a=p.parse_args();s=Store(a.db)
    run=s.db.execute('SELECT run_id FROM sessions ORDER BY rowid DESC LIMIT 1').fetchone()[0]
    trial=trial_for(s.db,run);streams={};last=0
    if not trial:raise ValueError('No configured trial')
    try:
        while datetime.now(timezone.utc).timestamp()<datetime.fromisoformat(trial['end']).timestamp()+240:
            last=process(s,run,trial,streams,last,datetime.now(timezone.utc));time.sleep(2)
        with s.db:s.db.execute("UPDATE cross_trial SET status='completed' WHERE run_id=?",(run,))
    finally:s.close()
if __name__=='__main__':main()
