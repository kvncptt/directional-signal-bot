"""Dashboard admission policy: fail closed while a raw setup awaits a decision."""
import json


def policy_for(db,run):
    if not db.execute("SELECT 1 FROM sqlite_master WHERE name='trend_policy'").fetchone():return None
    p=db.execute('SELECT * FROM trend_policy WHERE run_id=?',(run,)).fetchone()
    return dict(p) if p else None


def annotate(db,run,sid,records):
    policy=policy_for(db,run)
    if not policy:return [{**dict(r),'admission':'BASELINE','gate_reason':'Before trend filtering was enabled.'} for r in records]
    decisions={(r['symbol'],r['idx']):r for r in db.execute('SELECT * FROM trend_decisions WHERE run_id=? AND strategy=?',(run,sid))}
    output=[]
    for record in records:
        r=dict(record);d=decisions.get((r.get('symbol'),r['idx']))
        if r['timestamp']<policy['effective_at']:
            r.update(admission='BASELINE',gate_reason=('Historical review: '+d['reason']) if d else 'Before trend filtering was enabled.')
        elif d:
            r.update(admission='APPROVED' if d['approved'] else 'BLOCKED',gate_reason=d['reason'])
        else:r.update(admission='CHECKING',gate_reason='Waiting for trend validation; not an admitted signal.')
        if d:r['trend_context']=json.loads(d['context'])
        output.append(r)
    return output


def current_context(db,run,pair):
    if not policy_for(db,run):return None
    row=db.execute('SELECT context FROM trend_state WHERE run_id=? AND symbol=?',(run,pair)).fetchone()
    return json.loads(row[0]) if row else None
