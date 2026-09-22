import unittest
from dataclasses import replace
from directional_bot.quality import check
from directional_bot.models import Candle
from directional_bot.config import load
from directional_bot.features import Features
from directional_bot.readiness import progress
from test_bot import series

class QualityTest(unittest.TestCase):
    def candle(self):return Candle('USD_CAD','1m','2026-09-22T12:03:00+00:00',1,1.001,1,1.0002)
    def test_wick_and_strategy_scope(self):
        c=self.candle();self.assertFalse(check(c,'08','UP')[0]);self.assertTrue(check(c,'02','UP')[0])
        self.assertTrue(check(c,'08','DOWN')[0])
    def test_cooldown_expiry(self):
        c=replace(self.candle(),close=1.001)
        self.assertFalse(check(c,'08','UP','2026-09-22T12:01:00+00:00')[0])
        self.assertTrue(check(c,'08','UP','2026-09-22T12:00:00+00:00')[0])
    def test_progress_matches_raw_vote(self):
        from directional_bot.strategies import evaluate
        cfg=load();f=Features(cfg)
        for c in series(350):
            f.update(c)
            if len(f.rows)<2:continue
            votes={v.strategy:v.direction for v in evaluate(f.rows,cfg)}
            for sid in ('01','02','03','08'):
                for direction in ('UP','DOWN'):
                    checks=progress(f.rows,cfg,sid,direction)
                    if votes[sid]==direction:self.assertTrue(all(x['met'] for x in checks))
                    if all(x['met'] for x in checks):self.assertEqual(votes[sid],direction)
    def test_hot_expiry_and_stale_feed(self):
        import tempfile
        from pathlib import Path
        from datetime import datetime,timedelta
        from directional_bot.storage import Store
        from directional_bot.engine import Engine
        from directional_bot.readiness import attach
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'db.sqlite3';store=Store(path);engine=Engine(load(),store)
            c=self.candle();engine.ingest(c,predict=False)
            now=datetime.fromisoformat(c.timestamp)+timedelta(seconds=30)
            feed={'id':'08','strategy_id':'08','pair':'USD_CAD','state':'live','last_close':c.timestamp,'trend':None,'trades':[{'admission':'APPROVED','timestamp':c.timestamp,'direction':'UP'}]}
            state={'run_id':engine.run_id,'phase':'collecting','strategies':[feed]}
            self.assertEqual(attach(path,state,now)['strategies'][0]['heat']['state'],'HOT')
            self.assertNotEqual(attach(path,state,now+timedelta(seconds=30))['strategies'][0]['heat']['state'],'HOT')
            feed['strategy_id']='01'
            self.assertEqual(attach(path,state,now+timedelta(seconds=30))['strategies'][0]['heat']['state'],'HOT')
            feed['strategy_id']='08'
            feed['state']='stale'
            self.assertEqual(attach(path,state,now)['strategies'][0]['heat']['state'],'OFFLINE')
            feed['state']='live';feed['last_close']=(now+timedelta(minutes=3)).isoformat()
            self.assertNotEqual(attach(path,state,now+timedelta(minutes=3))['strategies'][0]['heat']['state'],'HOT')
            store.close()
