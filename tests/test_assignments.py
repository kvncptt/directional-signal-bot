import json
import tempfile
import unittest
from pathlib import Path
from datetime import datetime,timezone
from dataclasses import replace
from directional_bot.session import PAIRS,ASSIGNMENTS,session_config,setup,apply_assignments
from directional_bot.engine import Engine
from directional_bot.storage import Store
from directional_bot.admission import annotate
from directional_bot.trend_guard import setup as guard_setup
from directional_bot.chart_data import chart_snapshot
from test_bot import series

class AssignmentTest(unittest.TestCase):
    def test_reassignment_keeps_history_and_does_not_replay(self):
        store=Store(':memory:');cfg=session_config()
        cfg['symbol_strategies']={pair:[sid] for sid,pair in PAIRS.items()}
        engine=Engine(cfg,store)
        c=replace(series(1)[0],symbol='NZD_USD')
        engine.ingest(c,predict=False)
        store.prediction(engine.run_id,c,0,'04',1,'UP','RANGE',{})
        resumed=Engine.restore(store,engine.run_id)
        apply_assignments(resumed,datetime.now(timezone.utc))
        apply_assignments(resumed,datetime.now(timezone.utc))
        saved=json.loads(store.db.execute('SELECT config FROM runs').fetchone()[0])
        self.assertEqual(saved['symbol_strategies']['NZD_USD'],['01'])
        self.assertEqual(len(saved['assignment_history']),1)
        self.assertEqual(store.db.execute('SELECT source FROM predictions').fetchone()[0],'04')
        self.assertEqual(store.db.execute('SELECT COUNT(*) FROM candles').fetchone()[0],1)
        store.close()

    def test_decisions_with_same_strategy_and_index_are_pair_isolated(self):
        store=Store(':memory:');guard_setup(store.db)
        run=store.create_run(session_config(),'paper','test');stamp='2026-09-22T00:00:00+00:00'
        with store.db:
            store.db.execute('INSERT INTO trend_policy VALUES(?,?,?,?)',(run,stamp,'{}',stamp))
            for pair,ok in [('EUR_USD',1),('NZD_USD',0)]:
                store.db.execute('INSERT INTO trend_decisions VALUES(?,?,?,?,?,?,?,?)',(run,pair,'01',200,ok,pair,'{}','live'))
        rows=annotate(store.db,run,'01',[{'symbol':pair,'idx':200,'timestamp':stamp} for pair in ('EUR_USD','NZD_USD')])
        self.assertEqual([r['admission'] for r in rows],['APPROVED','BLOCKED'])
        store.close()

    def test_reassigned_chart_uses_new_strategy_indicators(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'test.sqlite3';store=Store(path);setup(store)
            engine=Engine(session_config(),store);now=datetime.now(timezone.utc).isoformat()
            with store.db:store.db.execute('INSERT INTO sessions(run_id,deadline,heartbeat,phase) VALUES(?,?,?,?)',(engine.run_id,now,now,'collecting'))
            for c in series(150):engine.ingest(replace(c,symbol='NZD_USD'),predict=False)
            view=chart_snapshot(path,'04')
            self.assertEqual(view['pair'],'NZD_USD');self.assertEqual(view['strategy_id'],'01')
            self.assertEqual([l['name'] for l in view['lines'][:4]],['SMA 6','SMA 14','SMA 50','RSI 5'])
            self.assertEqual(view['confirmations'],[])
            store.close()
