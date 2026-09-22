import json
import tempfile
import unittest
from dataclasses import replace
from datetime import datetime,timezone
from pathlib import Path
from directional_bot.chart_data import chart_snapshot
from directional_bot.features import Features
from directional_bot.engine import Engine
from directional_bot.session import session_config,setup,PAIRS
from directional_bot.storage import Store
from test_bot import series


class ChartTest(unittest.TestCase):
    def test_chart_uses_full_indicator_history_and_selected_pair(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'chart.sqlite3';store=Store(path);setup(store)
            cfg=session_config();cfg['symbol_strategies']={pair:[sid] for sid,pair in PAIRS.items()};engine=Engine(cfg,store)
            with store.db:store.db.execute('INSERT INTO sessions(run_id,deadline,heartbeat,phase) VALUES(?,?,?,?)',(engine.run_id,'2026-09-21T21:00:00+00:00',datetime.now(timezone.utc).isoformat(),'collecting'))
            data=series(150)
            for sid,pair in PAIRS.items():
                for c in data:engine.ingest(replace(c,symbol=pair),predict=False)
            for sid,pair in PAIRS.items():
                chart=chart_snapshot(path,sid)
                self.assertEqual(chart['pair'],pair)
                self.assertEqual(len(chart['candles']),150)
                self.assertTrue(chart['lines'])
                self.assertEqual(chart['candles'][-1]['close'],data[-1].close)
            actual=chart_snapshot(path,'01')
            features=engine.streams[('EUR_USD','1m')]
            self.assertAlmostEqual(actual['lines'][0]['data'][-1]['value'],features.rows[-1]['ma'][6])
            self.assertAlmostEqual(next(x for x in actual['lines'] if x['name']=='RSI 5')['data'][-1]['value'],features.rows[-1]['rsi']['01'])
            self.assertEqual(actual['candles'][-1]['time'],int(datetime.fromisoformat(data[-1].timestamp).timestamp()))
            # Confirmations are stamped at when known, never on the old pivot.
            for sid,key in [('05','zigzag'),('07','fractal')]:
                chart=chart_snapshot(path,sid)
                rows=engine.streams[(PAIRS[sid],'1m')].rows
                expected=[int(datetime.fromisoformat(r['candle'].timestamp).timestamp()) for r in rows if r[key]]
                self.assertEqual([c['time'] for c in chart['confirmations']],expected)
            store.close()
    def test_missing_database_and_invalid_strategy(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(chart_snapshot(Path(d)/'none','01')['candles'],[])
            with self.assertRaises(ValueError):chart_snapshot(Path(d)/'none','09')
