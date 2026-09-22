"""Local read-only dashboard. All data and credentials stay on this computer."""
import argparse
import csv
import io
import json
import sqlite3
from datetime import datetime,timezone
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse,parse_qs
from .session import PAIRS,NAMES,deadline_today,strategy_for
from .chart_data import chart_snapshot
from . import london,market_clock,readiness,horizons
from .admission import annotate,policy_for,current_context
from .cross_trial import EXTRA,trial_for

WEB=Path(__file__).with_name('web')


def snapshot(path):
    base={'phase':'waiting','deadline':deadline_today().isoformat(),'now':datetime.now(timezone.utc).isoformat(),'strategies':[], 'run_id':None}
    for sid,pair in PAIRS.items():base['strategies'].append({'id':sid,'name':NAMES[sid],'pair':pair,'state':'waiting','trades':[],'summary':{},'last_close':None,'price':None,'message':''})
    if not Path(path).exists():return base
    db=sqlite3.connect(f'file:{Path(path).resolve()}?mode=ro',uri=True);db.row_factory=sqlite3.Row
    try:
        if not db.execute("SELECT 1 FROM sqlite_master WHERE name='sessions'").fetchone():return base
        row=db.execute('SELECT * FROM sessions ORDER BY rowid DESC LIMIT 1').fetchone()
        if not row:return base
        cfg=json.loads(db.execute('SELECT config FROM runs WHERE id=?',(row['run_id'],)).fetchone()[0])
        base['paired_strategies']=len(set(strategy_for(cfg,f) for f in PAIRS))==4
        base.update(dict(row));base['trend_policy']=policy_for(db,row['run_id']);base['now']=datetime.now(timezone.utc).isoformat()
        heartbeat_age=(datetime.now(timezone.utc)-datetime.fromisoformat(row['heartbeat'])).total_seconds()
        if row['phase'] in ('collecting','settling','weekend_pause') and heartbeat_age>120:base['phase']='disconnected'
        trial=trial_for(db,row['run_id']);base['cross_trial']=trial
        if trial:
            for virtual,(feed_id,sid) in EXTRA.items():
                base['strategies'].append({'id':virtual,'pair':PAIRS[feed_id],'strategy_id':sid,'name':NAMES[sid],'trades':[],'summary':{},'last_close':None,'price':None,'state':'waiting','message':''})
        for strategy in base['strategies']:
            feed_id,override=EXTRA.get(strategy['id'],(strategy['id'],None));sid=override or strategy_for(cfg,feed_id)
            strategy.update(strategy_id=sid,name=NAMES[sid])
            feed=db.execute('SELECT * FROM feeds WHERE run_id=? AND strategy=?',(row['run_id'],feed_id)).fetchone()
            if feed:strategy.update({k:feed[k] for k in ('state','last_close','price','message')})
            if override and trial:
                age=(datetime.now(timezone.utc)-datetime.fromisoformat(trial['heartbeat'])).total_seconds()
                if base['now']>=trial['end']:strategy.update(state='completed',message='Today’s parallel trial has ended; saved results remain available.')
                elif age>30:strategy.update(state='stale',message='Parallel strategy evaluator is unavailable.')
            if base['phase']=='disconnected':strategy['state']='stale'
            records=db.execute('''SELECT a.idx,a.timestamp,a.symbol,a.direction,a.entry,a.regime,
              a.outcome AS result_1m,a.future_close AS close_1m,
              b.outcome AS result_3m,b.future_close AS close_3m
              FROM predictions a JOIN predictions b ON a.run_id=b.run_id AND a.symbol=b.symbol AND a.timeframe=b.timeframe AND a.idx=b.idx AND a.source=b.source
              WHERE a.run_id=? AND a.source=? AND a.symbol=? AND a.horizon=1 AND b.horizon=3 ORDER BY a.timestamp DESC''',(row['run_id'],sid,strategy['pair'])).fetchall()
            strategy['trades']=annotate(db,row['run_id'],sid,records)
            strategy['trend']=current_context(db,row['run_id'],strategy['pair'])
            strategy['blocked_count']=sum(t['admission']=='BLOCKED' for t in strategy['trades'])
            records=[t for t in strategy['trades'] if t['admission'] in ('BASELINE','APPROVED')]
            for h in (1,3):
                values=[r[f'result_{h}m'] for r in records]
                counts={k:values.count(k) for k in ('WIN','LOSS','TIE')}
                counts['PENDING']=values.count(None)
                n=sum(counts[k] for k in ('WIN','LOSS','TIE'))
                counts['rate']=counts['WIN']/n if n else None
                strategy['summary'][str(h)]=counts
        return base
    finally:db.close()


def handler(db_path):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_GET(self):
            if self.headers.get('Host') not in (f'127.0.0.1:{self.server.server_port}',f'localhost:{self.server.server_port}'):
                self.send_error(403);return
            target=urlparse(self.path)
            if target.path=='/api/state':
                data=json.dumps(horizons.attach(readiness.attach(db_path,snapshot(db_path)) if Path(db_path).exists() else snapshot(db_path))).encode();mime='application/json'
            elif target.path=='/api/market-clock':
                data=json.dumps(market_clock.snapshot()).encode();mime='application/json'
            elif target.path=='/api/london':
                data=json.dumps(london.snapshot(db_path)).encode();mime='application/json'
            elif target.path=='/api/chart':
                sid=parse_qs(target.query).get('strategy',['01'])[0]
                if sid not in PAIRS and sid not in EXTRA:self.send_error(400);return
                data=json.dumps(chart_snapshot(db_path,sid)).encode();mime='application/json'
            elif target.path=='/export.csv':
                state=snapshot(db_path);sid=parse_qs(target.query).get('strategy',[''])[0]
                if sid not in PAIRS and sid not in EXTRA:self.send_error(400);return
                strat=next(s for s in state['strategies'] if s['id']==sid)
                output=io.StringIO();writer=csv.DictWriter(output,fieldnames=['timestamp','symbol','direction','entry','regime','result_1m','close_1m','result_3m','close_3m','admission','gate_reason'],extrasaction='ignore');writer.writeheader();writer.writerows(strat['trades'])
                data=output.getvalue().encode();mime='text/csv'
            elif target.path in ('/','/app.js','/style.css','/chart.js','/focus.js','/market-clock.js','/vendor/lightweight-charts.js'):
                name='index.html' if target.path=='/' else target.path[1:]
                data=(WEB/name).read_bytes();mime='text/html' if name=='index.html' else 'text/css' if name.endswith('.css') else 'text/javascript'
            else:self.send_error(404);return
            self.send_response(200);self.send_header('Content-Type',mime+'; charset=utf-8');self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');self.send_header('Content-Security-Policy',"default-src 'self'; style-src 'self'; script-src 'self'; connect-src 'self'; frame-ancestors 'none'")
            self.end_headers();self.wfile.write(data)
    return Handler


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--db',default='data/dashboard.sqlite3');p.add_argument('--port',type=int,default=8877);a=p.parse_args()
    stop=london.start_worker(a.db)
    with ThreadingHTTPServer(('127.0.0.1',a.port),handler(a.db)) as server:
        print(f'Dashboard: http://127.0.0.1:{a.port}',flush=True)
        try:server.serve_forever()
        except KeyboardInterrupt:pass
        finally:stop.set()


if __name__=='__main__':main()
