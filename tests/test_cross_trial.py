import json,unittest
from datetime import datetime,timezone,timedelta
from unittest.mock import patch
from directional_bot.storage import Store
from directional_bot.session import setup,session_config
from directional_bot.trend_guard import setup as guard_setup
from directional_bot.cross_trial import process
from directional_bot.models import Candle,Vote

class CrossTrialTests(unittest.TestCase):
 def test_fresh_only_idempotent_exact_outcomes(self):
  s=Store(':memory:');setup(s);guard_setup(s.db);cfg=session_config();cfg['warmup']=1
  run=s.create_run(cfg,'paper','test');start=datetime(2026,9,22,14,tzinfo=timezone.utc)
  s.db.execute('CREATE TABLE cross_trial(run_id TEXT PRIMARY KEY,start TEXT,end TEXT,heartbeat TEXT,status TEXT)')
  trial={'start':start.isoformat(),'end':(start+timedelta(minutes=3)).isoformat()}
  s.db.execute('INSERT INTO cross_trial VALUES(?,?,?,?,?)',(run,trial['start'],trial['end'],trial['start'],'running'))
  streams={};last=0
  with patch('directional_bot.cross_trial.evaluate',return_value=[Vote('02','UP','test')]):
   for idx,m in enumerate((-1,0,1,3)):
    t=start+timedelta(minutes=m)
    c=Candle(symbol='EUR_USD',timeframe='1m',timestamp=t.isoformat(),open=1,high=1.1,low=.9,close=1+idx*.001,volume=1,complete=True)
    s.record_candle(run,c,idx);s.db.commit()
    last=process(s,run,trial,streams,last,t)
   rows=s.db.execute('SELECT timestamp,horizon,outcome FROM predictions ORDER BY id').fetchall()
   self.assertEqual(len(rows),4)
   self.assertEqual(rows[0]['outcome'],'WIN')
   self.assertEqual(rows[1]['outcome'],'WIN')
   self.assertTrue(all(trial['start']<=r['timestamp']<trial['end'] for r in rows))
   # A restart warms indicators but does not duplicate or manufacture older live signals.
   process(s,run,trial,{},0,start+timedelta(minutes=4))
   self.assertEqual(s.db.execute('SELECT count(*) FROM predictions').fetchone()[0],4)
  s.close()

 def test_second_group_start_and_quality_filter(self):
  s=Store(':memory:');setup(s);guard_setup(s.db);cfg=session_config();cfg['warmup']=1
  run=s.create_run(cfg,'paper','test');start=datetime(2026,9,22,14,tzinfo=timezone.utc)
  trial={'start':start.isoformat(),'second_start':(start+timedelta(minutes=1)).isoformat(),'end':(start+timedelta(minutes=3)).isoformat()}
  s.db.execute('CREATE TABLE cross_trial(run_id TEXT PRIMARY KEY,start TEXT,end TEXT,heartbeat TEXT,status TEXT)')
  s.db.execute('INSERT INTO cross_trial VALUES(?,?,?,?,?)',(run,trial['start'],trial['end'],trial['start'],'running'))
  s.db.execute('INSERT INTO quality_policy VALUES(?,?,?)',(run,trial['start'],'{}'));s.db.commit()
  streams={};last=0
  with patch('directional_bot.cross_trial.evaluate',return_value=[Vote('08','UP','test')]),patch('directional_bot.cross_trial.decision',return_value=(True,'trend allowed')):
   for idx in range(2):
    t=start+timedelta(minutes=idx)
    c=Candle('AUD_USD','1m',t.isoformat(),1,1.01,1,1.001)
    s.record_candle(run,c,idx);s.db.commit();last=process(s,run,trial,streams,last,t)
   self.assertEqual(s.db.execute('SELECT count(*) FROM predictions').fetchone()[0],2)
   d=s.db.execute('SELECT * FROM trend_decisions').fetchone()
   self.assertEqual(d['approved'],0)
   self.assertIn('rejection wick',d['reason'])
   self.assertEqual(json.loads(d['context'])['quality_version'],'quality-v2')
  s.close()
