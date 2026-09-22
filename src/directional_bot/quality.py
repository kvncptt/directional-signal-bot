"""Prospective paper-only quality gate. Frozen version, no outcome inputs."""
from datetime import datetime
VERSION='quality-v2'
POLICY={'version':VERSION,'strategies':['08'],'opposing_wick_fraction':0.4,'cooldown_seconds':180,'status':'paper trial'}
def check(c,strategy,direction,last_approved=None):
    if strategy not in POLICY['strategies']:return True,'Quality trial not applied to this strategy.'
    if last_approved and 0 <= (datetime.fromisoformat(c.timestamp)-datetime.fromisoformat(last_approved)).total_seconds()<POLICY['cooldown_seconds']:
        return False,'Quality v2: previous approved signal on this pair is still within its 3-minute window.'
    width=c.high-c.low
    wick=(c.high-max(c.open,c.close) if direction=='UP' else min(c.open,c.close)-c.low)
    if width<=0 or wick/width>=POLICY['opposing_wick_fraction']-1e-9:
        return False,'Quality v2: opposing rejection wick is at least 40% of the entry candle range (or candle is flat).'
    return True,'Quality v2: rejection-wick and repeat-entry checks passed.'
