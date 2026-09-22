"""Rule fixtures verify every baseline emits both directions and rejects a broken gate."""
import unittest
from copy import deepcopy
from directional_bot.config import load
from directional_bot.features import Features
from directional_bot.strategies import evaluate
from test_bot import candle, series


class StrategyRulesTest(unittest.TestCase):
    def fixture(self,sid,direction):
        cfg=load();f=Features(cfg)
        for c in series(140):f.update(c)
        rows=deepcopy(f.rows);p=cfg["strategies"][sid]
        up=direction=="UP";sgn=1 if up else -1
        prev,cur=rows[-2:]
        prev["candle"]=candle(138,100-sgn,100)
        cur["candle"]=candle(139,100+sgn,100)
        def mas(a,b):
            prev["ma"][a]=100-sgn;prev["ma"][b]=100
            cur["ma"][a]=100+sgn;cur["ma"][b]=100
        def stoch(s,base=50):
            prev["stoch"][s]=(base-sgn,base)
            cur["stoch"][s]=(base+sgn,base)
        def macd(s):
            rows[-3]["macd"][s]=(-sgn,0,-sgn)
            prev["macd"][s]=(sgn,0.5*sgn,0.5*sgn)
            cur["macd"][s]=(2*sgn,sgn,sgn)
        if sid=="01":
            mas(p["fast"],p["middle"])
            prev["ma"][p["slow"]]=100-4*sgn
            cur["ma"][p["slow"]]=100-3*sgn
            cur["rsi"][sid]=90 if up else 10
        elif sid=="02":
            for j,n in enumerate(p["mas"]):
                cur["ma"][n]=100+(4-j)*sgn
                prev["ma"][n]=cur["ma"][n]-sgn
                rows[-3]["ma"][n]=100+(j-4)*sgn
            prev["ma"][p["anchor"]]=100-4*sgn
            cur["ma"][p["anchor"]]=100-3*sgn
            macd(sid)
        elif sid=="03":
            prev["ma"][p["ma"]]=cur["ma"][p["ma"]]=100
            stoch(sid,50 if up else 80)
        elif sid=="04":
            prev["ha"]=candle(138,100-sgn,100)
            cur["ha"]=candle(139,100+sgn,100)
            prev["bb"]=cur["bb"]=(98,100,102)
            stoch(sid,22 if up else 85)
        elif sid=="05":
            cur["zigzag"]={"direction":direction,"pivot_index":130,"confirmed_index":139}
            rows[130]["candle"]=candle(130,100-sgn,100)
            rows[130]["keltner"]=(98,102)
            prev["stoch"][sid]=(10,15) if up else (90,85)
            cur["stoch"][sid]=(30,20) if up else (70,80)
        elif sid=="06":
            prev["ma"][p["ma"]]=cur["ma"][p["ma"]]=100
            cur["donchian"]=(99,101)
            level=70 if up else 30
            prev["rsi"][sid]=level-sgn
            cur["rsi"][sid]=level+sgn
        elif sid=="07":
            prev["fractal"]={"direction":direction,"pivot_index":136,"confirmed_index":138}
            mas(p["fast"],p["slow"])
        elif sid=="08":
            mas(p["fast"],p["slow"]);stoch(sid);macd(sid)
        return rows,cfg

    def test_all_eight_up_and_down(self):
        for sid in load()["strategies"]:
            for direction in ("UP","DOWN"):
                with self.subTest(strategy=sid,direction=direction):
                    rows,cfg=self.fixture(sid,direction)
                    vote=next(v for v in evaluate(rows,cfg) if v.strategy==sid)
                    self.assertEqual(vote.direction,direction)
                    broken=deepcopy(rows)
                    if sid in ("01","06"):broken[-1]["rsi"][sid]=50
                    elif sid in ("02","08"):broken[-1]["macd"][sid]=(None,None,None)
                    elif sid in ("03","04","05"):broken[-1]["stoch"][sid]=(None,None)
                    else:broken[-2]["fractal"]=None
                    vote=next(v for v in evaluate(broken,cfg) if v.strategy==sid)
                    self.assertEqual(vote.direction,"NEUTRAL")

    def test_fractal_does_not_trade_on_confirmation_bar(self):
        rows,cfg=self.fixture("07","UP")
        rows[-1]["fractal"]=rows[-2]["fractal"]
        rows[-2]["fractal"]=None
        self.assertEqual(evaluate(rows,cfg)[6].direction,"NEUTRAL")

    def test_zigzag_provisional_extreme_not_a_signal(self):
        rows,cfg=self.fixture("05","DOWN")
        rows[-1]["zigzag"]=None
        self.assertEqual(evaluate(rows,cfg)[4].direction,"NEUTRAL")
