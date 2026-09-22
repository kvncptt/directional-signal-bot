"""Entry-condition progress, not predictive confidence. Completed candles only."""
from datetime import datetime,timezone,timedelta
import json,sqlite3
from pathlib import Path
from .features import Features
from .models import Candle
from .strategies import recent,evaluate
from .trend import decision
from .quality import check
from .cross_trial import FOCUS
CACHE={}

def progress(rows,cfg,sid,direction):
    if len(rows)<2:return []
    r,old=rows[-1],rows[-2];p=cfg['strategies'][sid];c=r['candle'];sign=1 if direction=='UP' else -1
    def positive(x):return x is not None and sign*x>0
    def ma(f,s):return recent(rows,lambda v:(v['ma'][f],v['ma'][s]),direction,p.get('freshness',1))
    checks=[]
    if sid=='01':
        anchor=r['ma'][p['slow']];prior=old['ma'][p['slow']];rsi=r['rsi'][sid]
        checks=[('Fresh MA cross',ma(p['fast'],p['middle'])),('Price beyond anchor',anchor is not None and (c.low>anchor if sign==1 else c.high<anchor)),('Anchor slope',anchor is not None and prior is not None and positive(anchor-prior)),('RSI confirmation',rsi is not None and (rsi>p['upper'] if sign==1 else rsi<=p['lower']))]
    elif sid=='02':
        ns=p['mas'];cluster=[r['ma'][n] for n in ns];anchor=r['ma'][p['anchor']];prior=old['ma'][p['anchor']];m,s,h=r['macd'][sid];m0,s0,_=old['macd'][sid]
        checks=[('MA stack',None not in cluster and all(positive(a-b) for a,b in zip(cluster,cluster[1:]))),('MA slopes',all(r['ma'][n] is not None and old['ma'][n] is not None and positive(r['ma'][n]-old['ma'][n]) for n in ns)),('Anchor price and slope',anchor is not None and prior is not None and positive(anchor-prior) and (c.low>anchor if sign==1 else c.high<anchor)),('Fresh MA cross',ma(ns[0],ns[-1])),('Fresh MACD cross',recent(rows,lambda v:v['macd'][sid][:2],direction,p['freshness'])),('MACD momentum',None not in (m,s,m0,s0) and positive(m-m0) and positive(s-s0)),('Histogram confirmation',len(rows)>=p['hist_bars'] and all(positive(v['macd'][sid][2]) for v in rows[-p['hist_bars']:]))]
    elif sid=='03':
        k,d=r['stoch'][sid];k0,_=old['stoch'][sid]
        checks=[('Directional candle',positive(c.close-c.open)),('Fresh price/MA cross',recent(rows,lambda v:(v['candle'].close,v['ma'][p['ma']]),direction,1)),('Fresh stochastic cross',recent(rows,lambda v:v['stoch'][sid],direction,1)),('Stochastic zone',None not in (k,k0) and (k>p['lower'] if sign==1 else k0>=p['upper'] and k<p['upper']))]
    elif sid=='08':
        m,s,h=r['macd'][sid];m0,s0,_=old['macd'][sid];k,d=r['stoch'][sid]
        checks=[('Fresh MA cross',ma(p['fast'],p['slow'])),('Fresh MACD cross',recent(rows,lambda v:v['macd'][sid][:2],direction,p['freshness'])),('Fresh stochastic cross',recent(rows,lambda v:v['stoch'][sid],direction,p['freshness'])),('MACD momentum',None not in (m,s,h,m0,s0) and positive(h) and positive(m-m0) and positive(s-s0)),('Stochastic agreement',None not in (k,d) and positive(k-d))]
    return [{'name':name,'met':bool(ok)} for name,ok in checks]

def attach(source,state,now=None):
    now=now or datetime.now(timezone.utc)
    db=sqlite3.connect(f'file:{Path(source).resolve()}?mode=ro',uri=True);db.row_factory=sqlite3.Row
    try:
        run=state.get('run_id')
        if not run:return state
        cfg=json.loads(db.execute('SELECT config FROM runs WHERE id=?',(run,)).fetchone()[0])
        has_quality=db.execute("SELECT 1 FROM sqlite_master WHERE name='quality_policy'").fetchone()
        qp=db.execute('SELECT * FROM quality_policy WHERE run_id=?',(run,)).fetchone() if has_quality else None
        state['quality_policy']=dict(qp) if qp else None
        for feed in state['strategies']:
            sid=feed.get('strategy_id',feed['id']);symbol=feed['pair'];horizon=FOCUS.get(sid,3)
            feed['primary_horizon']=horizon
            active=[t for t in feed['trades'] if t['admission']=='APPROVED' and datetime.fromisoformat(t['timestamp'])<=now<datetime.fromisoformat(t['timestamp'])+timedelta(minutes=horizon)]
            stale=state['phase']!='collecting' or feed['state']!='live' or not feed['last_close'] or (now-datetime.fromisoformat(feed['last_close'])).total_seconds()>90
            if stale:
                feed['heat']={'state':'OFFLINE','reason':'Live feed unavailable; setup status cannot be confirmed.','active':len(active)};continue
            if active:
                end=max(datetime.fromisoformat(t['timestamp'])+timedelta(minutes=horizon) for t in active)
                feed['heat']={'state':'HOT','reason':f'Approved paper signal inside its {horizon}-minute primary measurement window.','active':len(active),'expires':end.isoformat(),'direction':active[0]['direction']};continue
            key=(str(source),run,symbol,sid,feed['last_close'])
            if key not in CACHE:
                features=Features(cfg)
                for r in db.execute('SELECT payload FROM candles WHERE run_id=? AND symbol=? ORDER BY idx',(run,symbol)):features.update(Candle(**json.loads(r[0])))
                options={direction:progress(features.rows,cfg,sid,direction) for direction in ('UP','DOWN')}
                c=features.rows[-1]['candle'] if features.rows else None
                votes=evaluate(features.rows,cfg);raw=next(v.direction for v in votes if v.strategy==sid)
                for oldkey in list(CACHE):
                    if oldkey[:4]==key[:4]:del CACHE[oldkey]
                CACHE[key]=(options,c,raw)
            options,c,raw=CACHE[key];bias=(feed.get('trend') or {}).get('bias');direction=bias if bias in ('UP','DOWN') else max(options,key=lambda d:sum(x['met'] for x in options[d]))
            checks=options[direction];met=sum(x['met'] for x in checks);total=len(checks)
            ctx=feed.get('trend')
            if ctx and ctx.get('timestamp')!=feed['last_close']:
                feed['heat']={'state':'COLD','reason':'Waiting for trend validation of the latest completed candle.','active':0};continue
            allowed,reason=decision(ctx,direction) if ctx else (False,'Trend context is not available.')
            if allowed and qp and c and c.timestamp>=qp['effective_at']:
                approved=[t for t in feed['trades'] if t['admission']=='APPROVED' and t['timestamp']<c.timestamp]
                allowed,reason=check(c,sid,direction,max((t['timestamp'] for t in approved),default=None))
            warm=allowed and total>0 and met/total>=.6
            latest=next((t for t in feed['trades'] if t['timestamp']==feed['last_close']),None)
            explanation=reason if not allowed else 'Waiting for '+', '.join(x['name'].lower() for x in checks if not x['met']) if met<total else 'Conditions met; awaiting a new approved signal.'
            if latest and latest['admission'] in ('BLOCKED','CHECKING'):explanation=latest['gate_reason'];warm=False
            feed['heat']={'state':'WARM' if warm else 'COLD','reason':explanation,'direction':direction,'met':met,'total':total,'checks':checks,'raw_signal':raw,'regime':None,'active':0}
        return state
    finally:db.close()
