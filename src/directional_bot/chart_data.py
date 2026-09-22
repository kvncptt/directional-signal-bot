"""Render inputs from the same causal indicator implementation as the signal engine."""
import json
import sqlite3
from datetime import datetime
from pathlib import Path
from .features import Features
from .models import Candle
from .session import PAIRS,NAMES,strategy_for
from .trend import TrendContext
from .cross_trial import EXTRA
from .admission import annotate,current_context,policy_for

CACHE={}
COLORS=['#5ce4b3','#70aaff','#ffbe68','#d39bff','#ff8496','#b1c5da']
RULES={
 '01':'A fresh SMA 6/14 cross, directional SMA 50 anchor and RSI 5 above 70 (UP) or at/below 30 (DOWN).',
 '02':'Recently crossed, aligned moving averages plus a fresh MACD cross, directional slopes and two confirming histogram bars.',
 '03':'Price crosses SMA 50 while the stochastic crosses in the same direction and satisfies its zone filter.',
 '04':'Heikin Ashi reverses after an outer Bollinger touch, crosses the middle band and confirms with stochastic.',
 '05':'Keltner contact at the swing, confirmed ZigZag reversal and a recent directional stochastic cross.',
 '06':'Break of the prior Donchian range, price crossing SMA 45 and RSI crossing its directional band.',
 '07':'A confirmed fractal followed by a reversal-colored candle and a fresh SMA 6/14 cross.',
 '08':'Recent SMA, MACD and stochastic crosses agree, with current momentum still aligned.'}


def chart_snapshot(path,sid):
    route=sid
    sid,override=EXTRA.get(sid,(sid,None))
    if sid not in PAIRS:raise ValueError('Unknown strategy')
    actual=override or sid
    empty={'strategy':sid,'pair':PAIRS[sid],'name':NAMES[actual],'candles':[],'ha':[],'lines':[],'confirmations':[],'rule':RULES[actual],'signals':[],'run_id':None}
    if not Path(path).exists():return empty
    db=sqlite3.connect(f'file:{Path(path).resolve()}?mode=ro',uri=True);db.row_factory=sqlite3.Row
    try:
        db.execute('BEGIN')
        if not db.execute("SELECT 1 FROM sqlite_master WHERE name='sessions'").fetchone():return empty
        run=db.execute('SELECT r.id,r.config FROM sessions s JOIN runs r ON s.run_id=r.id ORDER BY s.rowid DESC LIMIT 1').fetchone()
        if not run:return empty
        cfg=json.loads(run['config']);actual=override or strategy_for(cfg,sid)
        empty.update(name=NAMES[actual],rule=RULES[actual],strategy_id=actual)
        raw=db.execute('SELECT idx,payload FROM candles WHERE run_id=? AND symbol=? ORDER BY idx',(run['id'],PAIRS[sid])).fetchall()
        if not raw:return empty
        key=(str(Path(path).resolve()),run['id'],route,raw[-1]['idx'],actual)
        def admission_view(result):
            signals=annotate(db,run['id'],actual,result['signals'])
            return {**result,'signals':[s for s in signals if s['admission'] in ('BASELINE','APPROVED')],
                    'blocked_signals':[s for s in signals if s['admission']=='BLOCKED'],
                    'trend':current_context(db,run['id'],PAIRS[sid]),'trend_policy':policy_for(db,run['id'])}
        if key in CACHE:return admission_view(CACHE[key])
        cfg=json.loads(run['config']);p=cfg['strategies'][actual];features=Features(cfg)
        for r in raw:features.update(Candle(**json.loads(r['payload'])))
        rows=features.rows
        def epoch(c):return int(datetime.fromisoformat(c.timestamp).timestamp())
        def bars(attr):
            return [{'time':epoch(r['candle']),**{k:getattr(r[attr],k) for k in ('open','high','low','close')}} for r in rows]
        result={**empty,'run_id':run['id'],'candles':bars('candle'),'ha':bars('ha'),'parameters':p}
        lines=[]
        def line(name,getter,pane=0,kind='line',levels=None):
            data=[]
            for r in rows:
                value=getter(r)
                if value is not None:data.append({'time':epoch(r['candle']),'value':value})
            lines.append({'name':name,'pane':pane,'kind':kind,'color':COLORS[len(lines)%len(COLORS)],'data':data,'levels':levels or []})
        def ma(n):line(f'SMA {n}',lambda r:r['ma'][n])
        if actual=='01':
            for n in (p['fast'],p['middle'],p['slow']):ma(n)
        if actual=='02':
            for n in p['mas']+[p['anchor']]:ma(n)
        if actual in ('03','06'):ma(p['ma'])
        if actual in ('07','08'):
            for n in (p['fast'],p['slow']):ma(n)
        if actual=='04':
            for i,name in enumerate(('BB lower','BB middle','BB upper')):line(name,lambda r,i=i:r['bb'][i])
        if actual=='05':
            for i,name in enumerate(('Keltner lower','Keltner upper')):line(name,lambda r,i=i:r['keltner'][i])
        if actual=='06':
            for i,name in enumerate(('Prior Donchian low','Prior Donchian high')):line(name,lambda r,i=i:r['donchian'][i])
        if actual in ('01','06'):line(f'RSI {p["rsi"]}',lambda r:r['rsi'][actual],1,levels=[p['lower'],p['upper']])
        if actual in ('02','08'):
            for i,name in enumerate(('MACD','MACD signal','MACD histogram')):line(name,lambda r,i=i:r['macd'][actual][i],1,'histogram' if i==2 else 'line',levels=[0] if i==0 else [])
        if actual in ('03','04','05','08'):
            pane=2 if actual=='08' else 1
            for i,name in enumerate(('Stochastic K','Stochastic D')):line(name,lambda r,i=i:r['stoch'][actual][i],pane,levels=[p.get('lower',20),p.get('upper',80)] if i==0 else [])
        trend=TrendContext()
        contexts=[trend.update(r['candle']) for r in rows]
        for name,field,color in [('Trend SMA 200','sma200','#ffffff'),('Completed M5 EMA 50','m5','#b9a4ff'),('Confirmed resistance','resistance','#ff8496'),('Confirmed support','support','#5ce4b3')]:
            points=[]
            for r,ctx in zip(rows,contexts):
                value=ctx[field] if field!='m5' else (ctx['m5']['slow'] if ctx['m5'] else None)
                if value is not None:points.append({'time':epoch(r['candle']),'value':value})
            lines.append({'name':name,'pane':0,'kind':'line','color':color,'data':points,'levels':[],'dashed':True})
        result['lines']=lines
        if actual in ('05','07'):
            field='zigzag' if actual=='05' else 'fractal'
            result['confirmations']=[{'time':epoch(r['candle']),'direction':r[field]['direction'],'name':field.title()+' confirmed'} for r in rows if r[field]]
        trades=db.execute('''SELECT a.symbol,a.idx,a.timestamp,a.direction,a.entry,a.regime,a.outcome result_1m,a.future_close close_1m,b.outcome result_3m,b.future_close close_3m
          FROM predictions a JOIN predictions b ON a.run_id=b.run_id AND a.symbol=b.symbol AND a.timeframe=b.timeframe AND a.source=b.source AND a.idx=b.idx
          WHERE a.run_id=? AND a.symbol=? AND a.source=? AND a.horizon=1 AND b.horizon=3 ORDER BY a.idx''',(run['id'],PAIRS[sid],actual)).fetchall()
        result['signals']=[{**dict(r),'time':int(datetime.fromisoformat(r['timestamp']).timestamp())} for r in trades]
        # At most one cached revision per strategy/database; never truncate warmup history.
        for old in list(CACHE):
            if old[0]==key[0] and old[2]==route:CACHE.pop(old,None)
        CACHE[key]=result
        return admission_view(result)
    finally:db.close()
