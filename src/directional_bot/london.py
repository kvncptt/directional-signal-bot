"""Persistent hourly London observation notes, independent of signal generation."""
import json,sqlite3,threading,logging
from datetime import datetime,timedelta,timezone
from pathlib import Path
from zoneinfo import ZoneInfo
from .admission import annotate
LONDON=ZoneInfo('Europe/London')

def bucket(timestamp):
    # Candle timestamps mark CLOSE: 09:00 belongs to the 08:00–09:00 hour.
    local=(datetime.fromisoformat(timestamp)-timedelta(microseconds=1)).astimezone(LONDON)
    if local.weekday()>=5 or not 8<=local.hour<17:return None
    return local.replace(minute=0,second=0,microsecond=0)

def next_open(now):
    local=now.astimezone(LONDON);start=local.replace(hour=8,minute=0,second=0,microsecond=0)
    if local>=start:start+=timedelta(days=1)
    while start.weekday()>=5:start+=timedelta(days=1)
    return start

def summarize(start,candles,now,symbol=None):
    end=start+timedelta(hours=1);cs=sorted(candles,key=lambda c:c['timestamp'])
    expected={(start.astimezone(timezone.utc)+timedelta(minutes=i)).isoformat() for i in range(1,61)}
    actual={c['timestamp'] for c in cs};finished=now>=end
    complete=actual==expected
    if not cs:return dict(hour=start.isoformat(),end=end.isoformat(),symbol=symbol,status='missing' if finished else 'forming',candles=0,open=None,close=None,high=None,low=None,change_pips=None,range_pips=None,note='No candles received for this hour.')
    first,last=cs[0],cs[-1];pip=.01 if first['symbol'].endswith('_JPY') else .0001
    move=(last['close']-first['open'])/pip;high=max(c['high'] for c in cs);low=min(c['low'] for c in cs)
    direction='UP' if move>1e-8 else 'DOWN' if move< -1e-8 else 'FLAT'
    middle=next((c for c in cs if datetime.fromisoformat(c['timestamp'])==start+timedelta(minutes=30)),None)
    first_half=None if middle is None else (middle['close']-first['open'])/pip
    second_half=None if middle is None else (last['close']-middle['close'])/pip
    reversal=first_half is not None and first_half*second_half<0
    status='complete' if complete and finished else 'incomplete' if finished else 'forming'
    text=f"{direction} {move:+.1f} pips; range {(high-low)/pip:.1f} pips."
    if reversal:text+=' The second half moved against the first half.'
    if status!='complete':text+=f' {len(actual)}/60 candles; observed movement only.'
    return dict(hour=start.isoformat(),end=end.isoformat(),symbol=first['symbol'],status=status,candles=len(actual),open=first['open'],close=last['close'],high=high,low=low,change_pips=move,range_pips=(high-low)/pip,first_half_pips=first_half,second_half_pips=second_half,note=text)

def paths(source):return Path(source).with_name('london-hourly.sqlite3')

def update(source,now=None):
    now=now or datetime.now(timezone.utc)
    source=Path(source)
    if not source.exists():return
    db=sqlite3.connect(f'file:{source.resolve()}?mode=ro',uri=True);db.row_factory=sqlite3.Row
    out=sqlite3.connect(paths(source),timeout=15)
    try:
        out.executescript('CREATE TABLE IF NOT EXISTS notes(run_id TEXT,symbol TEXT,hour TEXT,payload TEXT,PRIMARY KEY(run_id,symbol,hour)); CREATE TABLE IF NOT EXISTS metadata(key TEXT PRIMARY KEY,value TEXT);')
        out.execute('INSERT OR IGNORE INTO metadata VALUES(?,?)',('started',now.isoformat()))
        started=datetime.fromisoformat(out.execute("SELECT value FROM metadata WHERE key='started'").fetchone()[0])
        session=db.execute('SELECT * FROM sessions ORDER BY rowid DESC LIMIT 1').fetchone()
        if not session:return
        run=session['run_id'];groups={}
        for r in db.execute("SELECT payload FROM candles WHERE run_id=? AND timeframe='1m' ORDER BY timestamp",(run,)):
            c=json.loads(r[0]);start=bucket(c['timestamp'])
            if start is not None:groups.setdefault((c['symbol'],start),[]).append(c)
        first=db.execute('SELECT MIN(timestamp) FROM candles WHERE run_id=?',(run,)).fetchone()[0]
        symbols=[r[0] for r in db.execute('SELECT symbol FROM feeds WHERE run_id=?',(run,))]
        if first:
            hour=datetime.fromisoformat(first).astimezone(LONDON).replace(minute=0,second=0,microsecond=0)
            while hour<now:
                if hour.weekday()<5 and 8<=hour.hour<17:
                    for symbol in symbols:groups.setdefault((symbol,hour),[])
                hour+=timedelta(hours=1)
        trades={}
        for r in db.execute("SELECT * FROM predictions WHERE run_id=? AND horizon IN (1,3) AND source!='ensemble'",(run,)):
            trades.setdefault(r['source'],[]).append(r)
        annotated=[r for sid,rs in trades.items() for r in annotate(db,run,sid,rs)]
        for (symbol,start),candles in groups.items():
            note=summarize(start,candles,now,symbol);end=start+timedelta(hours=1)
            note['collection']='historical' if end<=started else 'live observation'
            entries=[t for t in annotated if t['symbol']==symbol and start<=datetime.fromisoformat(t['timestamp'])<end]
            note['outcomes']={}
            for h in (1,3):
                admitted=[t for t in entries if t['horizon']==h and t['admission'] in ('BASELINE','APPROVED')]
                note['outcomes'][str(h)]={k:sum((t['outcome'] or 'PENDING')==k for t in admitted) for k in ('WIN','LOSS','TIE','PENDING')}
            note['entries']=sum(t['horizon']==1 and t['admission'] in ('BASELINE','APPROVED') for t in entries)
            note['blocked']=sum(t['horizon']==1 and t['admission']=='BLOCKED' for t in entries)
            note['run_id']=run
            out.execute('INSERT OR REPLACE INTO notes VALUES(?,?,?,?)',(run,symbol,start.isoformat(),json.dumps(note)))
        out.execute('INSERT OR REPLACE INTO metadata VALUES(?,?)',('heartbeat',now.isoformat()));out.commit()
    finally:db.close();out.close()

def snapshot(source):
    now=datetime.now(timezone.utc);local=now.astimezone(LONDON)
    result={'window':'08:00–17:00 Europe/London · Monday–Friday','active':local.weekday()<5 and 8<=local.hour<17,'next_open':next_open(now).isoformat(),'notes':[],'heartbeat':None}
    path=paths(source)
    if not path.exists():return result
    db=sqlite3.connect(f'file:{path.resolve()}?mode=ro',uri=True)
    try:
        result['notes']=[json.loads(r[0]) for r in db.execute('SELECT payload FROM notes ORDER BY hour DESC,symbol LIMIT 144')]
        row=db.execute("SELECT value FROM metadata WHERE key='heartbeat'").fetchone();result['heartbeat']=row[0] if row else None
    except sqlite3.OperationalError:pass
    finally:db.close()
    return result

def start_worker(source):
    stop=threading.Event()
    def work():
        while not stop.is_set():
            try:update(source)
            except Exception:logging.exception('London hourly observation update failed')
            stop.wait(30)
    threading.Thread(target=work,daemon=True,name='london-hourly').start()
    return stop
