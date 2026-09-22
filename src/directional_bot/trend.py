"""Causal higher-timeframe trend and confirmed level context (policy v1).

M5 bars require all five consecutive M1 closes. An unfinished bucket never
contributes. A swing level becomes visible only two right bars after its pivot.
"""
from collections import deque
from datetime import datetime,timezone
from .indicators import Mean,Smooth,ATR,Fractal
from .models import Candle

POLICY={'version':'trend-v1','minute_sma':200,'slope_bars':20,'five_fast':20,'five_slow':50,'five_slope_bars':3,'level_lookback':120,'level_buffer_atr':0.5,'unknown_action':'block'}


class TrendContext:
    def __init__(self):
        self.sma=Mean(200);self.smas=deque(maxlen=21);self.atr=ATR(14)
        self.fast=Smooth(20);self.slow=Smooth(50);self.slows=deque(maxlen=4)
        self.bucket=[];self.bucket_end=None;self.m5=None
        self.pivot=Fractal(2);self.candles=[];self.levels=[];self.state={}
    def update(self,c):
        i=len(self.candles);self.candles.append(c)
        ma=self.sma.update(c.close);self.smas.append(ma);atr=self.atr.update(c)
        t=int(datetime.fromisoformat(c.timestamp).timestamp());end=((t-1)//300+1)*300
        if end!=self.bucket_end:self.bucket=[];self.bucket_end=end
        self.bucket.append(c)
        stamps=[int(datetime.fromisoformat(x.timestamp).timestamp()) for x in self.bucket]
        if t==end and stamps==list(range(end-240,end+1,60)):
            w=self.bucket
            bar=Candle(c.symbol,'5m',c.timestamp,w[0].open,max(x.high for x in w),min(x.low for x in w),w[-1].close,sum(x.volume for x in w))
            fast,slow=self.fast.update(bar.close),self.slow.update(bar.close);self.slows.append(slow)
            self.m5={'time':c.timestamp,'close':bar.close,'fast':fast,'slow':slow,'previous_slow':self.slows[0] if len(self.slows)==4 else None}
        pivot=self.pivot.update(c,i)
        if pivot:
            original=self.candles[pivot['pivot_index']]
            self.levels.append({'kind':'support' if pivot['direction']=='UP' else 'resistance','price':original.low if pivot['direction']=='UP' else original.high,'pivot_time':original.timestamp,'confirmed_time':c.timestamp,'index':i})
        self.levels=[x for x in self.levels if i-x['index']<=120]
        # Broken levels do not remain resistance/support in this first policy.
        self.levels=[x for x in self.levels if (c.close>=x['price'] if x['kind']=='support' else c.close<=x['price'])]
        resistance=min((x['price'] for x in self.levels if x['kind']=='resistance'),default=None)
        support=max((x['price'] for x in self.levels if x['kind']=='support'),default=None)
        minute='UNKNOWN';five='UNKNOWN'
        old=self.smas[0] if len(self.smas)==21 else None
        if ma is not None and old is not None:
            if c.close>ma and ma>old:minute='UP'
            elif c.close<ma and ma<old:minute='DOWN'
            else:minute='MIXED'
        if self.m5 and all(self.m5[k] is not None for k in ('fast','slow','previous_slow')) and (datetime.fromisoformat(c.timestamp)-datetime.fromisoformat(self.m5['time'])).total_seconds()<600:
            m=self.m5
            if m['close']>m['slow'] and m['fast']>m['slow'] and m['slow']>m['previous_slow']:five='UP'
            elif m['close']<m['slow'] and m['fast']<m['slow'] and m['slow']<m['previous_slow']:five='DOWN'
            else:five='MIXED'
        bias=minute if minute==five and minute in ('UP','DOWN') else 'UNCLEAR'
        self.state={'bias':bias,'minute_trend':minute,'five_minute_trend':five,'sma200':ma,'sma200_prior20':old,'m5':self.m5,'resistance':resistance,'support':support,'atr':atr,'timestamp':c.timestamp,'close':c.close,'version':POLICY['version']}
        return self.state


def decision(context,direction):
    if context['bias']=='UNCLEAR':return False,'Broader trend is unclear or still warming up; no entry.'
    if direction!=context['bias']:return False,f"Countertrend {direction}: M1 anchor and completed M5 trend both point {context['bias']}."
    level=context['resistance'] if direction=='UP' else context['support']
    if level is not None and context['atr'] is not None and abs(level-context['close'])<=POLICY['level_buffer_atr']*context['atr']:
        kind='resistance' if direction=='UP' else 'support'
        return False,f"Entry too close to confirmed {kind} at {level:.5f} (within 0.5 ATR)."
    return True,f"Aligned with {direction} broader trend; no nearby opposing confirmed level."
