"""Descriptive matched-entry horizon comparisons; never changes signal admission."""
from collections import Counter

VALID = {'WIN', 'LOSS', 'TIE'}


def compare(trades):
    approved = [t for t in trades if t['admission'] == 'APPROVED']
    rows = [t for t in approved if t.get('result_1m') in VALID and t.get('result_3m') in VALID]
    n = len(rows)
    counts = {str(h): dict(Counter(t[f'result_{h}m'] for t in rows)) for h in (1, 3)}
    wins = {h: counts[h].get('WIN', 0) for h in counts}
    lead = None if wins['1'] == wins['3'] else (1 if wins['1'] > wins['3'] else 3)
    return {'n': n, 'unresolved': len(approved)-n, 'counts': counts,
            'rates': {h: wins[h]/n if n else None for h in counts},
            'leader': lead, 'label': 'Collecting evidence' if not n else 'No clear preference' if lead is None else f'{lead}m early lean',
            'only_1m_wins': sum(t['result_1m']=='WIN' and t['result_3m']!='WIN' for t in rows),
            'only_3m_wins': sum(t['result_3m']=='WIN' and t['result_1m']!='WIN' for t in rows)}


def attach(state):
    groups = {}
    for feed in state['strategies']:
        sid = feed.get('strategy_id', feed['id'])
        groups.setdefault(sid, []).append(feed)
    result = {}
    for sid, feeds in groups.items():
        cohorts = {}
        trial = state.get('cross_trial')
        if trial and sid in ('03','08'):
            trial = {**trial, 'start':trial['second_start']} if trial.get('second_start') else None
        # Only strategy 08 changed entry rules in Quality v2.
        for feed in feeds:
            for t in feed['trades']:
                version = 'quality-v2' if sid == '08' and (t.get('trend_context') or {}).get('quality_version') == 'quality-v2' else 'trend-v1'
                if trial and trial['start'] <= t['timestamp'] and (trial.get('schedule')=='weekdays' or t['timestamp'] < trial['end']):version='parallel-trial'
                cohorts.setdefault(version, []).append(t)
        if sid == '08' and state.get('quality_policy'):
            cohorts.setdefault('quality-v2', [])
        current = 'quality-v2' if sid == '08' and state.get('quality_policy') else 'trend-v1'
        if trial:current='parallel-trial'
        detail = {}
        for version, trades in cohorts.items():
            pairs = {f['pair']: compare([t for t in trades if t['symbol']==f['pair']]) for f in feeds}
            overall = compare(trades)
            leaders = {p['leader'] for p in pairs.values() if p['leader'] is not None}
            overall['pair_disagreement'] = len(leaders)>1
            if overall['pair_disagreement']:
                overall['label'] += ' · pairs differ'
            detail[version] = {'overall': overall, 'pairs': pairs}
        detail.setdefault(current, {'overall': compare([]), 'pairs': {}})
        result[sid] = {'current': current, 'cohorts': detail}
    state['horizon_analysis'] = result
    return state
