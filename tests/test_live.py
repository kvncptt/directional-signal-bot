import io
import json
import os
import unittest
from datetime import datetime, timezone
from unittest.mock import patch
from urllib.parse import urlparse,parse_qs
from directional_bot.oanda import OandaData,MarketDataError
from directional_bot.live import monitor,strategy01_config
from directional_bot.engine import Engine
from directional_bot.storage import Store
from test_bot import candle,series


class Opener:
    def __init__(self,payload):self.payload=payload;self.requests=[]
    def open(self,request,timeout):
        self.requests.append(request)
        return io.StringIO(json.dumps(self.payload))


class LiveTest(unittest.TestCase):
    def test_oanda_read_and_close_time(self):
        payload={"instrument":"EUR_USD","granularity":"M1","candles":[{"time":"2025-01-01T00:00:00.000000000Z","complete":True,"volume":10,"mid":{"o":"1.1","h":"1.2","l":"1.0","c":"1.15"}},{"complete":False}]}
        opener=Opener(payload)
        with patch.dict(os.environ,{"OANDA_API_TOKEN":"test-secret","OANDA_ACCOUNT_ID":"123-456","OANDA_ENVIRONMENT":"practice"}):
            client=OandaData(opener=opener)
        data=client.fetch(after_close="2025-01-01T00:01:00+00:00")
        self.assertEqual(len(data),1)
        self.assertEqual(data[0].timestamp,"2025-01-01T00:01:00+00:00")
        req=opener.requests[0]
        self.assertEqual(req.method,"GET")
        self.assertEqual(urlparse(req.full_url).hostname,"api-fxpractice.oanda.com")
        q=parse_qs(urlparse(req.full_url).query)
        self.assertEqual(q["from"],["2025-01-01T00:00:00+00:00"])
        self.assertEqual(q["includeFirst"],["false"])
        self.assertNotIn("test-secret",repr(client))
    def test_missing_creds(self):
        with patch.dict(os.environ,{},clear=True):
            with self.assertRaises(ValueError):OandaData()
    def test_no_live_account_host(self):
        with patch.dict(os.environ,{"OANDA_ENVIRONMENT":"live"}):
            with self.assertRaises(ValueError):OandaData()
    def test_startup_and_stale_suppressed(self):
        data=series(130)
        class Provider:
            def fetch(self,count=300,after_close=None):
                return data[:125] if after_close is None else data[125:]
        cfg=strategy01_config()
        self.assertEqual(cfg["enabled_strategies"],["01"])
        store=Store(":memory:")
        try:
            e=Engine(cfg,store)
            output=[]
            monitor(e,Provider(),polls=1,emit=lambda text,**kw:output.append(json.loads(text)),now=lambda:datetime(2025,1,2,tzinfo=timezone.utc))
            self.assertEqual(store.db.execute("SELECT COUNT(*) FROM candles").fetchone()[0],130)
            self.assertEqual(store.db.execute("SELECT COUNT(*) FROM predictions").fetchone()[0],0)
            self.assertEqual(output[0]["event"],"ready")
            self.assertTrue(all(x["stale"] for x in output if x["event"]=="candle"))
        finally:store.close()
    def test_only_first_strategy_logged(self):
        from directional_bot.models import Vote
        cfg=strategy01_config();cfg["warmup"]=1
        store=Store(":memory:")
        try:
            e=Engine(cfg,store)
            with patch("directional_bot.engine.evaluate",return_value=tuple(Vote(f'{i:02d}',"UP","") for i in range(1,9))):
                signals=e.ingest(candle(0))
            self.assertEqual(len(signals),2)
            sources={r[0] for r in store.db.execute("SELECT source FROM predictions")}
            self.assertEqual(sources,{"01","ensemble"})
        finally:store.close()

class MeasurementTest(unittest.TestCase):
    def test_both_horizons_and_no_regime_gate(self):
        from directional_bot.models import Vote
        cfg=strategy01_config();cfg['warmup']=1
        self.assertFalse(cfg['skip_high_volatility'])
        self.assertEqual(cfg['horizons'],[1,3])
        store=Store(':memory:')
        try:
            e=Engine(cfg,store)
            with patch('directional_bot.engine.evaluate',return_value=(Vote('01','UP',''),)):
                e.ingest(candle(0,100))
            e.ingest(candle(1,101),predict=False)
            e.ingest(candle(2,100),predict=False)
            e.ingest(candle(3,99),predict=False)
            rows=store.db.execute("SELECT horizon,outcome,future_close FROM predictions WHERE source='01' ORDER BY horizon").fetchall()
            self.assertEqual([tuple(r) for r in rows],[(1,'WIN',101),(3,'LOSS',99)])
        finally:store.close()

    def test_missing_minutes_not_replaced_by_next_observed_candle(self):
        from directional_bot.models import Vote
        cfg=strategy01_config();cfg['warmup']=1
        store=Store(':memory:')
        try:
            e=Engine(cfg,store)
            with patch('directional_bot.engine.evaluate',return_value=(Vote('01','DOWN',''),)):
                e.ingest(candle(0,100))
            e.ingest(candle(3,99),predict=False)
            rows=store.db.execute("SELECT horizon,outcome FROM predictions WHERE source='01' ORDER BY horizon").fetchall()
            self.assertEqual([tuple(r) for r in rows],[(1,None),(3,'WIN')])
        finally:store.close()

    def test_recorder_reads_local_source(self):
        import tempfile
        from pathlib import Path
        from directional_bot.recorder import record
        from directional_bot.config import load
        with tempfile.TemporaryDirectory() as folder:
            src=Path(folder)/'source.sqlite3';dst=Path(folder)/'output.sqlite3'
            store=Store(src)
            e=Engine(load(),store,'paper','OANDA practice M1 midpoint live')
            for c in series(150):e.ingest(c,predict=False)
            store.close()
            with patch('builtins.print'):
                record(src,dst,once=True)
            out=Store(dst)
            try:
                self.assertEqual(out.db.execute('SELECT COUNT(*) FROM candles').fetchone()[0],150)
                cfg=json.loads(out.db.execute('SELECT config FROM runs').fetchone()[0])
                self.assertEqual(cfg['horizons'],[1,3])
            finally:out.close()
