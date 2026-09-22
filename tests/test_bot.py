import io
import json
import math
import random
import tempfile
import unittest
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from directional_bot.config import load, validate
from directional_bot.models import Candle, Vote, label
from directional_bot.data import CSVData, JSONLData
from directional_bot.indicators import Mean, Smooth, RSI, ATR, Stochastic, MACD, Bollinger, HeikinAshi, Fractal, ZigZag
from directional_bot.features import Features
from directional_bot.strategies import evaluate
from directional_bot.ensemble import combine
from directional_bot.engine import Engine
from directional_bot.storage import Store
from directional_bot.cli import main


def candle(i, close=100, op=None, high=None, low=None, symbol="TEST"):
    op = close if op is None else op
    return Candle(symbol,"1m",(datetime(2025,1,1,tzinfo=timezone.utc)+timedelta(minutes=i)).isoformat(),op,max(op,close)+1 if high is None else high,min(op,close)-1 if low is None else low,close)


def series(n=350):
    rng = random.Random(77)
    result = []
    price = 100
    for i in range(n):
        op = price
        price += math.sin(i/5)+rng.uniform(-0.5,0.5)
        result.append(candle(i,price,op))
    return result


class IndicatorsTest(unittest.TestCase):
    def test_sma_and_ema_seed(self):
        sma, ema = Mean(3),Smooth(3)
        self.assertEqual([sma.update(x) for x in [1,2,3,4]],[None,None,2,3])
        self.assertEqual([ema.update(x) for x in [1,2,3,4]],[None,None,2,3])
    def test_rsi(self):
        for values,expected in [([1,2,3,4],100),([4,3,2,1],0),([2,2,2,2],50)]:
            r = RSI(3)
            out = [r.update(x) for x in values]
            self.assertEqual(out[:3],[None]*3)
            self.assertEqual(out[-1],expected)
    def test_atr_gap(self):
        a = ATR(2)
        self.assertIsNone(a.update(candle(0,100)))
        self.assertEqual(a.update(candle(1,110)),6.5)
    def test_bollinger_population_sd(self):
        b = Bollinger(3,2)
        b.update(1);b.update(2)
        lo,mid,hi = b.update(3)
        self.assertEqual(mid,2)
        self.assertAlmostEqual(hi,2+2*math.sqrt(2/3))
        self.assertAlmostEqual(lo,2-2*math.sqrt(2/3))
    def test_stochastic_flat(self):
        s = Stochastic(2,1,1)
        c = candle(0,100,high=100,low=100)
        self.assertEqual(s.update(c),(None,None))
        self.assertEqual(s.update(c),(50,50))
    def test_macd_constant(self):
        m = MACD(2,3,2)
        out = [m.update(100) for _ in range(10)]
        self.assertEqual(out[-1],(0,0,0))
        self.assertIsNone(out[1][0])
    def test_heikin_ashi(self):
        h = HeikinAshi()
        a = h.update(candle(0,104,100,106,98))
        b = h.update(candle(1,106,104,108,102))
        self.assertEqual(a.close,102)
        self.assertEqual(b.open,102)
        self.assertEqual(b.close,105)
    def test_fractal_waits_right_bars(self):
        f = Fractal(2)
        out = [f.update(candle(i,x),i) for i,x in enumerate([5,4,2,4,5])]
        self.assertEqual(out[:4],[None]*4)
        self.assertEqual(out[-1],{"direction":"UP","pivot_index":2,"confirmed_index":4})
        self.assertIsNone(f.update(candle(5,6),5))
    def test_fractal_equal_extremes_abstain(self):
        f = Fractal(1)
        self.assertEqual([f.update(candle(i,x),i) for i,x in enumerate([4,3,3])],[None]*3)
    def test_zigzag_confirmation_not_backdated(self):
        z = ZigZag(1,2)
        out = [z.update(x,1,i) for i,x in enumerate([10,12,15,14,13])]
        self.assertEqual(out[:4],[None]*4)
        self.assertEqual(out[-1],{"direction":"DOWN","pivot_index":2,"confirmed_index":4})
        saved = deepcopy(out[-1])
        for i,x in enumerate([16,17,18],5): z.update(x,1,i)
        self.assertEqual(out[-1],saved)
    def test_donchian_excludes_current(self):
        cfg=load();cfg["strategies"]["06"]["donchian"]=2
        f=Features(cfg)
        f.update(candle(0,100));f.update(candle(1,101))
        r=f.update(candle(2,120))
        self.assertEqual(r["donchian"],(99,102))


class PipelineTest(unittest.TestCase):
    def setUp(self): self.cfg=load();self.store=Store(":memory:")
    def tearDown(self): self.store.close()
    def test_outcomes(self):
        for d in ("UP","DOWN"):
            self.assertEqual(label(d,100,100),"TIE")
        self.assertEqual(label("UP",100,101),"WIN")
        self.assertEqual(label("UP",100,99),"LOSS")
        self.assertEqual(label("DOWN",100,99),"WIN")
        self.assertEqual(label("DOWN",100,101),"LOSS")
    def test_no_execution_and_invalid_config(self):
        for key,val in [("execution_enabled",True),("horizons",[0]),("confidence_threshold",float("nan")),("min_active_votes",9)]:
            cfg=load();cfg[key]=val
            with self.assertRaises(ValueError):validate(cfg)
    def test_config_roundtrip(self):
        root=Path(__file__).resolve().parents[1]
        self.assertEqual(load(root/"config/default.json"),load())
    def test_ingestion_validation(self):
        e=Engine(self.cfg,self.store)
        c=candle(0)
        self.assertEqual(e.ingest(replace(c,complete=False)),[])
        self.assertEqual(e.streams,{})
        e.ingest(c);e.ingest(c)
        self.assertEqual(len(e.streams[("TEST","1m")].rows),1)
        with self.assertRaises(ValueError):e.ingest(replace(c,close=100.5))
        with self.assertRaises(ValueError):e.ingest(candle(-1))
        for kw in [dict(close=float("nan")),dict(low=101),dict(volume=-1)]:
            with self.assertRaises(ValueError):replace(c,**kw)
    def test_ensemble(self):
        votes=tuple(Vote(s,d,"") for s,d in [("01","UP"),("02","DOWN"),("03","UP")])
        cfg=load();cfg["confidence_threshold"]=0.5
        sig=combine(candle(0),votes,"RANGE",2,cfg)
        self.assertEqual(sig.direction,"UP")
        self.assertAlmostEqual(sig.confidence,1.55/2.1)
        self.assertEqual(sig.horizon,2)
        cfg["horizon_thresholds"]={"2":0.99}
        self.assertIsNone(combine(candle(0),votes,"RANGE",2,cfg))
        self.assertIsNone(combine(candle(0),votes,"HIGH_VOLATILITY",1,cfg))
    def test_tie_and_abstention(self):
        cfg=load()
        votes=(Vote("01","UP",""),Vote("02","DOWN",""))
        self.assertIsNone(combine(candle(0),votes,"RANGE",1,cfg))
        self.assertIsNone(combine(candle(0),votes[:1],"TREND",1,cfg))
    def test_exact_horizon_and_stream_isolation(self):
        cfg=load();cfg["warmup"]=1;cfg["horizons"]=[2]
        votes=(Vote("01","UP",""),Vote("02","UP",""))
        e=Engine(cfg,self.store)
        with patch("directional_bot.engine.evaluate",return_value=votes):
            e.ingest(candle(0,100))
            e.ingest(candle(0,200,symbol="OTHER"))
            e.ingest(candle(1,99))
            first=self.store.db.execute("SELECT * FROM predictions WHERE symbol='TEST' AND idx=0 AND source='ensemble'").fetchone()
            self.assertIsNone(first["outcome"])
            e.ingest(candle(2,101))
        first=self.store.db.execute("SELECT * FROM predictions WHERE symbol='TEST' AND idx=0 AND source='ensemble'").fetchone()
        self.assertEqual(first["outcome"],"WIN")
        self.assertEqual(first["future_close"],101)
        other=self.store.db.execute("SELECT outcome FROM predictions WHERE symbol='OTHER'").fetchall()
        self.assertTrue(all(r[0] is None for r in other))
    def test_statistics_ties_pending(self):
        run=self.store.create_run(self.cfg,"paper","test")
        c=candle(0)
        for source in ["01","ensemble"]:
            self.store.prediction(run,c,0,source,1,"UP","RANGE",{})
            self.store.prediction(run,c,0,source,3,"UP","RANGE",{})
        self.store.resolve(run,candle(1),1)
        rows=self.store.statistics(run)
        self.assertEqual(rows[0]["ties"],1)
        self.assertEqual(rows[0]["win_rate"],0)
        self.assertIsNone(rows[0]["decisive_win_rate"])
        self.assertEqual(rows[1]["pending"],1)
    def test_causal_prefix_invariance_all_strategies_and_regime(self):
        cfg=load();data=series()
        f=Features(cfg); snapshots=[]
        for c in data:
            row=f.update(c)
            snapshots.append((deepcopy(row),evaluate(f.rows,cfg)))
        for stop in [80,150,230]:
            prefix=Features(cfg)
            for c in data[:stop]:prefix.update(c)
            self.assertEqual((prefix.rows[-1],evaluate(prefix.rows,cfg)),snapshots[stop-1])
            # Replace all future candles with extreme movements; past stays identical.
            for i in range(stop,stop+10):prefix.update(candle(i,1000+i))
            self.assertEqual(prefix.rows[stop-1],snapshots[stop-1][0])
    def test_paper_backtest_identical(self):
        cfg=load();cfg["min_active_votes"]=1
        outputs=[]
        for mode in ("paper","backtest"):
            e=Engine(cfg,self.store,mode)
            out=[]
            for c in series():out.extend(s.to_dict() for s in e.ingest(c))
            outputs.append(out)
        self.assertTrue(outputs[0])
        self.assertEqual(*outputs)
    def test_csv_jsonl(self):
        root=Path(__file__).resolve().parents[1]
        data=list(CSVData(root/"data/sample.csv").candles())
        self.assertEqual(len(data),2400)
        from dataclasses import asdict
        self.assertEqual(list(JSONLData(io.StringIO(json.dumps(asdict(data[0])))).candles()),data[:1])
    def test_cli_end_to_end(self):
        root=Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as d:
            db=str(Path(d)/"test.sqlite3")
            output=str(Path(d)/"signals.jsonl")
            with patch("sys.stdout",new_callable=io.StringIO),patch("sys.stderr",new_callable=io.StringIO):
                self.assertEqual(main(["backtest","--data",str(root/"data/sample.csv"),"--db",db,"--signals-out",output]),0)
                self.assertEqual(main(["stats","--db",db]),0)
                self.assertEqual(main(["signals","--db",db]),0)
            signals=[json.loads(x) for x in Path(output).read_text().splitlines()]
            self.assertTrue(signals)
            self.assertIn("strategy_votes",signals[0])
    def test_failure_status(self):
        e=Engine(self.cfg,self.store)
        class Bad:
            def candles(self):
                yield candle(1)
                yield candle(0)
        with self.assertRaises(ValueError):list(e.replay(Bad()))
        self.assertEqual(self.store.db.execute("SELECT status FROM runs").fetchone()[0],"failed")


if __name__ == "__main__": unittest.main()
