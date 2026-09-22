"""Indicative weekday FX session windows in each financial centre's local time."""
from datetime import datetime,timedelta,time,timezone
from zoneinfo import ZoneInfo
SESSIONS=[('London','Europe/London',8,17,'london'),('Aussie · Sydney','Australia/Sydney',8,17,'sydney'),('Tokyo','Asia/Tokyo',9,18,'tokyo'),('New York','America/New_York',8,17,'newyork')]

def snapshot(now=None):
    now=now or datetime.now(timezone.utc);windows=[]
    for name,zone,opening,closing,key in SESSIONS:
        tz=ZoneInfo(zone);today=now.astimezone(tz).date()
        for offset in range(-2,4):
            date=today+timedelta(days=offset)
            if date.weekday()>=5:continue
            start=datetime.combine(date,time(opening),tz);end=datetime.combine(date,time(closing),tz)
            windows.append(dict(name=name,key=key,start=start.timestamp(),end=end.timestamp()))
    boundaries=sorted({v[k] for v in windows for k in ('start','end')});overlaps=[]
    for a,b in zip(boundaries,boundaries[1:]):
        active=[v['name'] for v in windows if v['start']<=a and v['end']>=b]
        if len(active)>=2:overlaps.append(dict(start=a,end=b,names=active))
    return dict(generated_at=now.timestamp(),sessions=[dict(name=n,zone=z,key=k,hours=f'{o:02}:00–{c:02}:00') for n,z,o,c,k in SESSIONS],windows=windows,overlaps=overlaps)
