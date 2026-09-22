"""OANDA practice candle reads only; no trading endpoints or redirect following."""
import json
import os
import re
import time
from datetime import datetime, timedelta
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, build_opener, HTTPRedirectHandler
from .models import Candle


class MarketDataError(RuntimeError):
    pass


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class OandaData:
    def __init__(self, symbol="EUR_USD", opener=None, sleep=time.sleep):
        if os.environ.get("OANDA_ENVIRONMENT", "practice") != "practice":
            raise ValueError("Only OANDA practice market data is supported")
        if not re.fullmatch(r"[A-Z0-9]+_[A-Z0-9]+", symbol):
            raise ValueError("Invalid OANDA instrument")
        self._token = os.environ.get("OANDA_API_TOKEN", "").strip()
        self._account = os.environ.get("OANDA_ACCOUNT_ID", "").strip()
        if not self._token or not re.fullmatch(r"[0-9-]+", self._account):
            raise ValueError("Set OANDA_API_TOKEN and OANDA_ACCOUNT_ID locally for your practice account; do not paste credentials into chat")
        self.symbol, self.opener, self.sleep = symbol, opener or build_opener(NoRedirect()), sleep

    def fetch(self, count=300, after_close=None):
        if type(count) is not int or not 1 <= count <= 5000:
            raise ValueError("count must be 1..5000")
        params = dict(granularity="M1", count=count, price="M", smooth="false")
        if after_close:
            # OANDA timestamps are candle OPEN times, our engine stores CLOSE times.
            start = datetime.fromisoformat(after_close)-timedelta(minutes=1)
            params.update({"from":start.isoformat(), "includeFirst":"false"})
        url = f"https://api-fxpractice.oanda.com/v3/accounts/{self._account}/instruments/{self.symbol}/candles?{urlencode(params)}"
        request = Request(url, headers={"Authorization":"Bearer "+self._token,"Accept-Datetime-Format":"RFC3339"}, method="GET")
        for attempt in range(3):
            try:
                with self.opener.open(request,timeout=15) as response:
                    payload = json.load(response)
                break
            except HTTPError as exc:
                status = exc.code
                exc.close()
                if status not in (429,500,502,503,504) or attempt==2:
                    raise MarketDataError(f"OANDA candle read failed (HTTP {status})") from None
            except (URLError,TimeoutError,OSError):
                if attempt==2: raise MarketDataError("OANDA connection failed after 3 attempts") from None
            except (ValueError,UnicodeError):
                raise MarketDataError("OANDA returned invalid JSON") from None
            self.sleep(2**attempt)
        try:
            if payload["instrument"]!=self.symbol or payload["granularity"]!="M1":
                raise ValueError("unexpected instrument/timeframe")
            candles=[]
            for raw in payload["candles"]:
                if type(raw["complete"]) is not bool: raise ValueError("completion flag")
                if not raw["complete"]: continue
                dt=datetime.fromisoformat(raw["time"].replace("Z","+00:00"))
                close_time=(dt+timedelta(minutes=1)).isoformat()
                mid=raw["mid"]
                candles.append(Candle(self.symbol,"1m",close_time,*(float(mid[k]) for k in ("o","h","l","c")),float(raw["volume"])))
            candles.sort(key=lambda c:c.timestamp)
            if len({c.timestamp for c in candles})!=len(candles): raise ValueError("duplicate candle")
            return candles
        except (KeyError,TypeError,ValueError,OverflowError):
            raise MarketDataError("OANDA returned malformed candle data") from None
