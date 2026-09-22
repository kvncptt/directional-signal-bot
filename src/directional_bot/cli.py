import argparse
import json
import sys
import sqlite3
from contextlib import nullcontext
from pathlib import Path
from .config import load
from .data import CSVData, JSONLData
from .engine import Engine
from .storage import Store
from .oanda import MarketDataError


def main(argv=None):
    parser = argparse.ArgumentParser(description="Local directional signals. Execution is unavailable.")
    sub = parser.add_subparsers(dest="command", required=True)
    for command in ("backtest", "paper"):
        p = sub.add_parser(command)
        p.add_argument("--data", required=True, help="CSV or JSONL; '-' reads JSONL from stdin")
        p.add_argument("--format", choices=("csv","jsonl"), default="csv")
        p.add_argument("--config", default=None)
        p.add_argument("--db", default="data/signals.sqlite3")
        p.add_argument("--signals-out", help="Write emitted signal objects as JSONL")
    p = sub.add_parser("live", help="OANDA practice M1 data, strategy 01 only")
    p.add_argument("--symbol", default="EUR_USD")
    p.add_argument("--config")
    p.add_argument("--db", default="data/live-strategy01.sqlite3")
    p.add_argument("--interval", type=int, default=5)
    p.add_argument("--polls", type=int, default=0, help="0 runs until Ctrl+C")
    p = sub.add_parser("stats")
    p.add_argument("--db", default="data/signals.sqlite3")
    p.add_argument("--run")
    p.add_argument("--json", action="store_true")
    p = sub.add_parser("signals")
    p.add_argument("--db", default="data/signals.sqlite3")
    p.add_argument("--run")
    p.add_argument("--limit", type=int, default=20)
    args = parser.parse_args(argv)
    store = None
    engine = None
    try:
        if args.command == "live":
            from .live import run_live
            return run_live(args)
        if args.command in ("stats","signals"):
            if not Path(args.db).is_file(): raise ValueError("database does not exist")
            store = Store(args.db)
            run = args.run or store.latest_run()
            if not store.db.execute("SELECT 1 FROM runs WHERE id=?",(run,)).fetchone(): raise ValueError("unknown run")
            if args.command == "signals":
                if args.limit < 1: raise ValueError("limit must be positive")
                for r in store.signals(run,args.limit):
                    payload = json.loads(r.pop("payload"))
                    print(json.dumps({**payload,**r}))
            else:
                rows = store.statistics(run)
                if args.json: print(json.dumps({"run_id":run,"statistics":rows},indent=2))
                else:
                    print(f"Run {run} | confidence = agreement, not win probability")
                    print("SOURCE    HORIZON REGIME           TOTAL  WIN LOSS TIE PENDING WIN_RATE")
                    for r in rows:
                        rate = "n/a" if r["win_rate"] is None else f'{100*r["win_rate"]:.1f}%'
                        print(f'{r["source"]:<9} {r["horizon"]:>7} {r["regime"]:<16} {r["total"]:>5} {r["wins"]:>4} {r["losses"]:>4} {r["ties"]:>3} {r["pending"]:>7} {rate:>8}')
            return 0
        cfg = load(args.config)
        if args.signals_out and args.data != "-" and Path(args.signals_out).resolve() == Path(args.data).resolve():
            raise ValueError("signals output must not overwrite input")
        if args.signals_out and Path(args.signals_out).resolve() == Path(args.db).resolve():
            raise ValueError("signals output must not overwrite database")
        if args.data != "-" and Path(args.data).resolve() == Path(args.db).resolve():
            raise ValueError("database must not overwrite input")
        store = Store(args.db)
        engine = Engine(cfg,store,args.command,args.data)
        count = 0
        output = open(args.signals_out,"w") if args.signals_out else nullcontext(None)
        with output as out:
            if args.data == "-":
                provider = JSONLData(sys.stdin)
                for signal in engine.replay(provider):
                    count += 1
                    text = json.dumps(signal.to_dict())
                    if out: out.write(text+"\n"); out.flush()
                    if args.command == "paper": print(text,flush=True)
            elif args.format == "jsonl":
                with open(args.data) as f:
                    for signal in engine.replay(JSONLData(f)):
                        count += 1
                        text = json.dumps(signal.to_dict())
                        if out: out.write(text+"\n")
                        if args.command == "paper": print(text,flush=True)
            else:
                for signal in engine.replay(CSVData(args.data)):
                    count += 1
                    text = json.dumps(signal.to_dict())
                    if out: out.write(text+"\n")
                    if args.command == "paper": print(text,flush=True)
        print(json.dumps({"run_id":engine.run_id,"signals":count,"db":args.db,"execution_enabled":False}),file=sys.stderr)
        return 0
    except (ValueError, OSError, KeyError, TypeError, sqlite3.Error, MarketDataError) as e:
        if engine and store:
            store.finish(engine.run_id, "failed")
        print(f"Error: {e}",file=sys.stderr)
        return 2
    finally:
        if store: store.close()


if __name__ == "__main__": raise SystemExit(main())
