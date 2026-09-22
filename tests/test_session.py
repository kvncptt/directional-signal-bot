import tempfile
import unittest
from dataclasses import replace
from datetime import datetime,timedelta,timezone
from pathlib import Path
from unittest.mock import patch
from directional_bot.session import collect,eligible,PAIRS,ASSIGNMENTS,session_config
from directional_bot.dashboard import snapshot
from directional_bot.models import Vote
from directional_bot.storage import Store
from test_bot import series,candle


class SessionTest(unittest.TestCase):
    def test_cutoff_and_staleness(self):
        end=datetime(2025,1,1,17,tzinfo=timezone.utc)
        c=replace(candle(0),timestamp=(end-timedelta(minutes=1)).isoformat())
        self.assertTrue(eligible(c,end-timedelta(seconds=30),end))
        self.assertFalse(eligible(c,end,end))
        self.assertFalse(eligible(c,end+timedelta(minutes=5),end))
        self.assertFalse(eligible(c,end-timedelta(minutes=2),end))
    def test_two_pairs_per_remaining_strategy(self):
        cfg=session_config()
        self.assertEqual(len(set(PAIRS.values())),8)
        for sid,pair in PAIRS.items():self.assertEqual(cfg['symbol_strategies'][pair],[ASSIGNMENTS[sid]])
        self.assertEqual(cfg['horizons'],[1,3])
    def test_eight_feeds_isolated_and_dashboard(self):
        data=series(121)
        class Fake:
            def __init__(self,pair):self.pair=pair
            def fetch(self,count,after_close):
                return [replace(c,symbol=self.pair) for c in (data[:120] if after_close is None else data[120:])]
        now=datetime.fromisoformat(data[-1].timestamp)+timedelta(seconds=10)
        with tempfile.TemporaryDirectory() as d:
            db=Path(d)/'session.sqlite3'
            with patch('builtins.print'),patch('directional_bot.engine.evaluate',return_value=tuple(Vote(s,'UP','test') for s in PAIRS)):
                collect(db,now+timedelta(hours=1),client_factory=Fake,clock=lambda:now,sleep=lambda n:None,max_cycles=2)
            state=snapshot(db)
            self.assertEqual(len(state['strategies']),8)
            for strat in state['strategies']:
                self.assertEqual(len(strat['trades']),1)
                self.assertEqual(strat['trades'][0]['symbol'],PAIRS[strat['id']])
                self.assertEqual(strat['summary']['1']['PENDING'],1)
            store=Store(db)
            try:
                rows=store.db.execute("SELECT DISTINCT symbol,source FROM predictions WHERE source!='ensemble'").fetchall()
                self.assertEqual({tuple(r) for r in rows},{(pair,ASSIGNMENTS[sid]) for sid,pair in PAIRS.items()})
            finally:store.close()
    def test_past_deadline_refuses_start(self):
        now=datetime.now(timezone.utc)
        with self.assertRaises(ValueError):collect('unused.sqlite3',now-timedelta(seconds=1),clock=lambda:now)
    def test_empty_dashboard(self):
        with tempfile.TemporaryDirectory() as d:
            state=snapshot(Path(d)/'absent.sqlite3')
            self.assertEqual(state['phase'],'waiting')
            self.assertEqual(len(state['strategies']),8)

class WeekdayTest(unittest.TestCase):
    def test_weekday_boundaries_detroit(self):
        from directional_bot.session import weekday_open,next_weekend,weekend_settling
        fri=datetime(2026,9,26,3,59,tzinfo=timezone.utc)
        sat=fri+timedelta(minutes=1)
        mon=datetime(2026,9,28,4,tzinfo=timezone.utc)
        self.assertTrue(weekday_open(fri));self.assertFalse(weekday_open(sat));self.assertTrue(weekday_open(mon))
        self.assertEqual(next_weekend(fri),sat)
        self.assertTrue(weekend_settling(sat));self.assertFalse(weekend_settling(sat+timedelta(minutes=4)))
    def test_resume_does_not_duplicate_saved_candles_or_predictions(self):
        from directional_bot.engine import Engine
        from directional_bot.config import load
        from test_bot import series
        store=Store(':memory:')
        try:
            engine=Engine(load(),store)
            for c in series(150):engine.ingest(c)
            before=store.db.execute('SELECT COUNT(*) FROM predictions').fetchone()[0]
            resumed=Engine.restore(store,engine.run_id)
            self.assertEqual(resumed.last,engine.last)
            self.assertEqual(resumed.streams[('TEST','1m')].rows,engine.streams[('TEST','1m')].rows)
            self.assertEqual(store.db.execute('SELECT COUNT(*) FROM predictions').fetchone()[0],before)
            self.assertEqual(store.db.execute('SELECT COUNT(*) FROM candles').fetchone()[0],150)
        finally:store.close()
    def test_weekend_pause_does_not_fetch(self):
        class Fake:
            def __init__(self,pair):pass
            def fetch(self,**kw):raise AssertionError('Weekend should not poll')
        now=datetime(2026,9,26,16,tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as d:
            db=Path(d)/'weekend.sqlite3'
            with patch('builtins.print'):
                collect(db,now-timedelta(hours=1),client_factory=Fake,clock=lambda:now,sleep=lambda n:None,max_cycles=1,weekdays=True)
            store=Store(db)
            try:
                self.assertEqual(store.db.execute('SELECT COUNT(*) FROM candles').fetchone()[0],0)
                self.assertEqual(store.db.execute('SELECT schedule FROM sessions').fetchone()[0],'weekdays')
            finally:store.close()
