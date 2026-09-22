import json
import tempfile
import unittest
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from datetime import datetime,timezone
from directional_bot.trend import TrendContext,decision
from directional_bot.trend_guard import setup,process
from directional_bot.admission import annotate
from directional_bot.storage import Store
from directional_bot.config import load
from test_bot import candle


class TrendTest(unittest.TestCase):
    def test_aligned_and_countertrend(self):
        for direction,sign in [('UP',1),('DOWN',-1)]:
            context=TrendContext()
            for i in range(400):
                p=100+sign*i*.1
                state=context.update(candle(i,p,high=p+.03,low=p-.03))
            self.assertEqual(state['bias'],direction)
            self.assertTrue(decision(state,direction)[0])
            self.assertFalse(decision(state,'DOWN' if sign==1 else 'UP')[0])
    def test_unfinished_m5_not_used(self):
        context=TrendContext()
        for i in range(301):state=context.update(candle(i,100+i*.1))
        saved=deepcopy(state['m5'])
        for i in range(301,305):state=context.update(candle(i,500))
        self.assertEqual(saved,state['m5'])
    def test_incomplete_m5_bucket_skipped(self):
        context=TrendContext()
        for i in (1,2,4,5):state=context.update(candle(i,100))
        self.assertIsNone(state['m5'])
    def test_near_resistance_and_support(self):
        base={'bias':'UP','resistance':101,'support':99,'atr':1,'close':100.8}
        self.assertFalse(decision(base,'UP')[0])
        base.update(bias='DOWN',close=99.2)
        self.assertFalse(decision(base,'DOWN')[0])
        base['bias']='UNCLEAR'
        self.assertFalse(decision(base,'DOWN')[0])
    def test_levels_not_known_before_confirmation(self):
        ctx=TrendContext();states=[]
        for i,p in enumerate([100,101,105,102,101]):states.append(deepcopy(ctx.update(candle(i,p))))
        self.assertIsNone(states[2]['resistance'])
        self.assertIsNone(states[3]['resistance'])
        self.assertEqual(states[4]['resistance'],106)
    def test_prefix_invariance(self):
        a=TrendContext();b=TrendContext()
        for i in range(300):x=deepcopy(a.update(candle(i,100+i*.1)));b.update(candle(i,100+i*.1))
        prefix=deepcopy(b.state)
        for i in range(300,320):a.update(candle(i,200))
        self.assertEqual(x,prefix)
    def test_admission_preserves_baseline_and_fails_closed(self):
        with tempfile.TemporaryDirectory() as d:
            store=Store(Path(d)/'test.sqlite3');setup(store.db)
            run=store.create_run(load(),'paper','test')
            with store.db:store.db.execute('INSERT INTO trend_policy VALUES(?,?,?,?)',(run,candle(2).timestamp,'{}',candle(2).timestamp))
            rows=[{'symbol':candle(i).symbol,'idx':i,'timestamp':candle(i).timestamp} for i in (1,3)]
            results=annotate(store.db,run,'01',rows)
            self.assertEqual(results[0]['admission'],'BASELINE')
            self.assertEqual(results[1]['admission'],'CHECKING')
            store.close()
    def test_guard_blocks_new_raw_setup_and_preserves_history(self):
        with tempfile.TemporaryDirectory() as d:
            store=Store(Path(d)/'guard.sqlite3');setup(store.db)
            run=store.create_run(load(),'paper','test')
            with store.db:
                store.db.execute('INSERT INTO trend_policy VALUES(?,?,?,?)',(run,candle(350).timestamp,'{}',candle(350).timestamp))
                for i in range(401):
                    price=100-i*.1;c=candle(i,price,high=price+.03,low=price-.03)
                    store.record_candle(run,c,i)
                    if i in (300,400):
                        for h in (1,3):store.prediction(run,c,i,'02',h,'UP','RANGE',{})
            last=process(store.db,run,{},0)
            self.assertGreater(last,0)
            records=[{'symbol':candle(i).symbol,'idx':i,'timestamp':candle(i).timestamp} for i in (300,400)]
            results=annotate(store.db,run,'02',records)
            self.assertEqual([r['admission'] for r in results],['BASELINE','BLOCKED'])
            self.assertIn('Countertrend',results[1]['gate_reason'])
            self.assertEqual(store.db.execute('SELECT COUNT(*) FROM predictions').fetchone()[0],4)
            store.close()
