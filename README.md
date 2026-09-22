# Directional Signal Bot

## Collaborator setup

See [CONTRIBUTING.md](CONTRIBUTING.md) for installation, testing, and the contribution workflow. This repository contains code and synthetic sample data; local credentials, live databases, logs, private PDFs, and analysis exports stay on each computer.


A local Python 3.11+ signal-only implementation of eight strategy families from the Trading Bot project's PDFs. It predicts **UP or DOWN over N subsequent complete candles**, evaluates hypothetical entries, and keeps an auditable SQLite history. OANDA practice candle reads are available through environment credentials; no order API or live execution path is included. Setting `execution_enabled` to anything other than `false` is rejected.

## Start

From this `directional-bot` directory:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -e .
.venv/bin/directional-bot backtest --data data/sample.csv --config config/default.json --db data/demo.sqlite3 --signals-out data/demo-signals.jsonl
.venv/bin/directional-bot stats --db data/demo.sqlite3
.venv/bin/directional-bot signals --db data/demo.sqlite3 --limit 5
```

The runtime has no third-party dependencies. To run without installing:

```sh
PYTHONPATH=src python3 -m directional_bot backtest --data data/sample.csv
PYTHONPATH=src python3 -m directional_bot stats
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

`data/sample.csv` contains 2,400 **synthetic** candles generated with a fixed seed by `tools/generate_sample.py`. Its results test the pipeline and do not demonstrate an edge. The CLI prints a run ID and signal count to stderr; statistics and signal JSON go to stdout. `stats --json` returns machine-readable data. Use `--run RUN_ID` to inspect earlier runs.

## Data and paper mode

CSV headers:

```csv
symbol,timeframe,timestamp,open,high,low,close,volume,complete
EUR_USD,1m,2025-01-01T00:01:00+00:00,1.10,1.12,1.09,1.11,100,true
```

`timestamp` is the **candle close time**, with a timezone. Convert providers' open timestamps before ingestion. OHLC prices must be positive, finite and internally consistent; volume defaults to zero. `complete` defaults to true, so explicitly mark unfinished candles false. Incomplete candles are ignored. Each symbol/timeframe stream must arrive chronologically. Exact repetitions of the most recent completed candle are ignored; revisions or older candles are rejected. Different streams can be interleaved and never share indicators or outcomes.

```sh
.venv/bin/directional-bot paper --data data/sample.csv --db data/paper.sqlite3
.venv/bin/directional-bot paper --data exported-candles.jsonl --format jsonl
cat exported-candles.jsonl | .venv/bin/directional-bot paper --data -
```

JSONL uses the same field names and one JSON object per line. A long-lived producer can pipe newly completed candles into `paper --data -`; signals print immediately and each candle commits to SQLite. EOF ends the run. Paper replay processes files as fast as possible, with no artificial market-time delay.

Every invocation starts an isolated run. Process restart does **not** resume an old run's pending predictions; replay the complete input into a new run to rebuild state. The Python `MarketData` protocol exposes `candles() -> Iterable[Candle]`, and `Engine.ingest(candle)` supports incremental adapters. CSV, JSONL and OANDA practice M1 polling are included; TradingView webhooks are not included. A local dashboard is available through `python -m directional_bot.dashboard`; see the later dashboard sections.

## Signals and outcomes

Each ensemble signal contains symbol, timeframe, timestamp, raw close entry, integer candle horizon, UP/DOWN direction, confidence, confidence kind, regime, all eight strategy votes and their effective weights. Heikin Ashi values are used only for strategy 04's indicator decisions; entry and outcome prices always use real OHLC closes.

A signal issued on candle `i` is settled only on candle `i + horizon` of that same stream:

- UP wins when that future close is strictly above entry.
- DOWN wins when it is strictly below entry.
- Equal prices are `TIE`, reported separately, and count as non-wins in `win_rate`.
- `decisive_win_rate` excludes ties. Unresolved tail signals remain pending and are excluded from both rates.

Horizons count **observed complete candles**, not elapsed wall time. Gaps/weekends extend elapsed expiry; no missing candles are fabricated. The timeframe label is metadata, not an automatic resampling instruction. Use contiguous data when matching a fixed clock expiry. Entries assume the just-closed candle's price is obtainable; there is no latency, spread, payout, fill or profit model. Performance reports measure directional correctness, not options returns. Predictions can overlap; their results are not independent samples.

## Confidence and regime

Confidence is the winning side's weighted vote total divided by the total of active nonzero-weight votes. Neutral votes do not count. It is an **uncalibrated agreement score, not probability of winning**. Correlated strategies can agree and still be wrong. A directional tie, too few active votes, insufficient agreement or the default high-volatility gate produces no ensemble signal.

Defaults require two active votes and 0.70 agreement. Base strategy weights and regime multipliers are fixed configuration assumptions, not trained weights. Regime detection uses only observed candles: 20-bar efficiency ratio >= 0.35 marks TREND; otherwise RANGE. ATR(14) > 1.8 times its 50-value average overrides this to HIGH_VOLATILITY. High-volatility ensemble signals are skipped by default, while standalone strategy predictions remain logged for analysis.

Edit `config/default.json` or provide a partial JSON override via `--config`. It controls horizons, global/per-horizon thresholds, warmup, active vote count, regime settings, weights and strategy parameters. Per-horizon overrides use string keys, for example `"horizon_thresholds": {"1": 0.8}`. Weights of zero disable a strategy's ensemble contribution, not its independent diagnostic logging. The default 120-bar warmup is additional to indicator-specific readiness. Longer custom periods continue to abstain until ready.

## Strategy specifications

See [the rule mapping](docs/strategy-specifications.md) for exact variants, numeric assumptions, and confirmation delays. The PDFs contain multiple recipes rather than one executable specification. This version implements one documented baseline per family, not every optional indicator/variant.

ZigZag only emits immutable confirmed directional-change events. Fractals require completed candles to the right of a candidate and are never used at their historical pivot time. Donchian breakouts compare with the prior channel, excluding the current candle. The engine uses exactly the same chronological processing for paper and backtest. It never fits weights or thresholds using evaluation outcomes.

## Persistence and reports

SQLite tables store runs (mode, config, source and status), accepted candles, and predictions (standalone strategies and ensemble) with outcomes and settlement timestamps. Each candle's logging, outcome settlement and new predictions are committed together. Runs isolate repeated backtests to avoid accidental double counting. Reports group by strategy/ensemble, horizon and issuance regime; inspect a single run by ID. Source config is saved in full; the original input path is saved but input file content is not copied beyond accepted candle records.

The engine retains feature history in memory for auditability and pivot lookup. This first version is intended for local research and modest streams; unlimited retention, restart recovery and very large dataset optimization are future work. Strict combinations can produce very few signals; absence of a signal is a valid result.

## Project layout

- `src/directional_bot/`: validated candle model, adapters, indicators, feature engine, eight strategies, ensemble, SQLite and CLI.
- `config/default.json`: complete reproducible defaults.
- `data/sample.csv`: deterministic synthetic input.
- `docs/strategy-specifications.md`: rules and source-to-code choices.
- `docs/source-manifest.json`: PDF filenames and hashes.
- `tests/`: indicator values, all eight UP/DOWN gates, confirmation timing, future-prefix invariance, stream isolation, horizons, outcomes, CLI and paper/backtest equivalence.

Before interpreting accuracy, evaluate untouched chronological market data using parameters fixed before that evaluation. Neither the PDFs' promotional examples nor this synthetic demonstration establishes predictive performance.

## OANDA demo live data: strategy 01

The `live` command reads only OANDA practice midpoint M1 candles. It requires `OANDA_API_TOKEN` and `OANDA_ACCOUNT_ID` in the launching Terminal environment. Obtain the token through the demo account's Manage API Access page. Do not paste credentials into chat or put them in source code. `.env` files are not loaded automatically.

In macOS Terminal (zsh), from this project directory:

```sh
read -rs 'OANDA_API_TOKEN?Paste OANDA demo API token (hidden): '
echo
read -r 'OANDA_ACCOUNT_ID?OANDA demo account ID: '
export OANDA_API_TOKEN OANDA_ACCOUNT_ID
export OANDA_ENVIRONMENT=practice
.venv/bin/directional-bot live --symbol EUR_USD
```

The prompts keep the token out of shell command history. The bot inherits credentials from this Terminal; exporting them does not change an already-running Codex session. Leave Terminal open; Ctrl+C stops the monitor. A new Terminal requires these credentials again.

Live defaults are strategy 01 only, one-minute candles and exact one-minute and three-minute prediction horizons. Other strategies' votes are disabled. Confidence will be 1.0 when the only enabled strategy fires; that denotes a single aligned vote, not 100% accuracy. The high-volatility gate is disabled for strategy 01 directional measurement, so it does not filter out strategy signals.

Startup loads at least 300 completed candles for indicator warmup without issuing historical signals. It then polls every five seconds. OANDA open timestamps are converted to close timestamps. Incomplete candles are ignored; catch-up candles older than 90 seconds update indicators and resolve outcomes without issuing stale predictions. `ready`, `candle`, `poll` and `signal` JSON events show connection progress, data freshness and decisions. No new complete candles during market closures is expected. Three bounded retries cover transient request errors; a continuing error stops the run with a sanitized message. Restart begins a new run.

```sh
.venv/bin/directional-bot live --symbol EUR_USD --polls 1
.venv/bin/directional-bot stats --db data/live-strategy01.sqlite3
```

The first command checks authentication, warms up indicators and polls once. Successful live authentication must be checked with your own credentials; automated tests use fake API responses. API references: [OANDA authentication](https://developer.oanda.com/rest-live-v20/authentication/) and [candle endpoint](https://developer.oanda.com/rest-live-v20/pricing-ep/).

## Recording every strategy 01 signal at 1m and 3m

The local recorder follows the existing OANDA monitor's saved candles, without another API connection or credentials:

```sh
.venv/bin/python -m directional_bot.recorder
```

Leave the original OANDA monitor running. The recorder writes `data/strategy01-measurements.sqlite3`, and refreshes `data/strategy01-measurements.csv` with one row per strategy 01 signal: timestamp, direction, entry, 1m close/result, 3m close/result, regime and collection type. It has no volatility filter. `historical_replay` rows are causal reconstructions from previously collected candles; `live` rows were issued on candles closing after the recorder started. Historical rows include the source's startup candles after the strategy's warmup. They must not be confused with signals emitted live at that time.

Outcomes use the exact close timestamp plus 1 or 3 minutes. A missing expiry candle leaves that result pending; the next available candle is never substituted. UP wins on a strictly higher close; DOWN on a strictly lower close; equal prices are TIE. This measures raw directional change with no execution, payouts, costs or position sizing. Each signal has two independent results and overlapping signals are allowed.

```sh
.venv/bin/directional-bot stats --db data/strategy01-measurements.sqlite3
```

Strategy `01` and `ensemble` rows are two representations of the same signals; do not add them together. The CSV uses only `01`. The recorder follows one specific source run; if you restart the original OANDA monitor, restart the recorder to follow its new run. Restarting the recorder creates a new measurement run and rebuilds from the source history; SQLite preserves earlier runs, while the CSV shows the newest run. Data collection pauses if the computer sleeps or the original feed stops. A source process killed without clean shutdown can leave a stale `running` status; inspect the newest candle timestamp to verify freshness.

## Live dashboard: eight strategies, eight pairs

Open http://127.0.0.1:8877 after starting the local dashboard:

```sh
.venv/bin/python -m directional_bot.dashboard
```

In the Terminal that holds your OANDA demo credentials, stop the old single-pair monitor with Ctrl+C and start the new collector:

```sh
.venv/bin/python -m directional_bot.session --until 2026-09-21T17:00:00-04:00
```

The collector polls eight pairs concurrently and uses exactly one strategy per pair:

| Strategy | Pair |
|---|---|
| 01 MA Stack RSI | EUR/USD |
| 02 Multi MA MACD | GBP/USD |
| 03 MA Stochastic | AUD/USD |
| 04 Bollinger Heikin Ashi | NZD/USD |
| 05 Keltner Stoch ZigZag | USD/JPY |
| 06 Donchian Breakout | USD/CHF |
| 07 Fractal Extreme Reversal | USD/CAD |
| 08 Oscillator Confluence | USD/SGD |

The dashboard shows connection freshness, each strategy's signal list, entry price, exact 1m and 3m close/results, and CSV export. Click a strategy card to select its separate list. The win-rate denominator includes ties and excludes pending outcomes. Different pairs mean observed results reflect both the strategy and the market; this session is not a controlled strategy comparison.

SQLite stores sessions and feed health in `data/dashboard.sqlite3`, alongside accepted candles and per-strategy predictions. Historical startup candles warm indicators but create no signals. High-volatility conditions do not filter standalone strategy observations. API errors are isolated per pair and displayed; unavailable instruments remain visibly in error instead of being silently replaced. Prices use OANDA midpoint candles, not executable quotes.

The collector stops issuing new signals at the specified deadline even if a network request started earlier. It continues reading candles until 3 minutes 30 seconds after the cutoff to label final outcomes, then exits. The dashboard remains available for reviewing saved results. Missing exact expiry candles remain pending. Computer sleep, network loss or closing the collector Terminal can interrupt data collection; missed data can be caught up while it is still running, but stale catch-up bars do not generate new signals. After 120 seconds without a collector heartbeat, the dashboard explicitly reports an interrupted feed.

Default `--until` is 5 PM on the current Detroit calendar date; starting after that deadline is rejected. Specify another timezone-aware deadline explicitly for a different session. Restarting starts a new run, which the dashboard selects automatically; previous runs remain in SQLite. The eight-pair session does not merge older single-pair measurement history into its live totals.

### Selected-pair live chart

Selecting a strategy now loads its one-minute chart, the same indicators used by its signal engine, and recorded entry arrows with exact raw entry-price dots. Moving averages and price channels overlay candles; RSI, stochastic and MACD use separate panels. Strategy 04 defaults to Heikin Ashi and offers a raw-candle view; its indicator calculations remain Heikin Ashi-based in both views. All entry/outcome prices remain raw midpoint closes.

Click **Latest signal**, an entry candle on the chart, or a signal's entry-time button in the table to show the entry-price line, at-entry indicator values, and 1m/3m results. **Latest candles** returns to the most recent 90 candles. Zoom and pan are preserved during refresh unless you are following the right edge.

The dashboard checks for updates every five seconds; new chart candles appear only after each one-minute candle is complete. Chart times are candle CLOSE times displayed in Detroit time, matching recorded signals. ZigZag/fractal dots mark confirmation time, never retrospective pivot time. Indicator values are reconstructed from the full stored candle history using the run's saved settings, not approximate frontend calculations. The chart backend caches each completed-candle revision. TradingView Lightweight Charts 5.2.0 is vendored locally with its Apache license and notice; no chart data or credentials are sent to TradingView.

### Trend-aligned admission (trend-v1)

The live session now has a separate admission layer. The original eight rules still produce raw strategy observations so their unfiltered outcomes remain measurable. Only observations approved by the trend guard are presented as new signals. This avoids changing the historical strategy specifications or deleting earlier losses.

Rules fixed in `trend.py`:

- M1 close must be above a rising SMA200 for UP, or below a falling SMA200 for DOWN. Slope compares today’s value with 20 candles earlier.
- Completed five-minute candles must agree: EMA20 above EMA50, five-minute close above EMA50, and EMA50 higher than three completed five-minute bars earlier for UP; mirror for DOWN.
- A five-minute candle requires all five consecutive one-minute closes. In-progress or incomplete five-minute buckets never influence the gate. Missing/warming/conflicting context means UNCLEAR and no admission.
- A confirmed five-bar fractal supplies a support/resistance level only after its two right candles close. Levels persist for up to 120 one-minute confirmations and are removed on a close through the level. UP within 0.5 ATR14 of surviving resistance is blocked; DOWN near support is blocked. This is a mechanical proximity test, not a full discretionary retest detector or a guarantee that a level will hold.

`trend_guard` follows the same session database without another OANDA connection. Its decisions store exact at-entry context, reason and policy version. It starts automatically with newly launched session collectors. The existing session received a separate guard process, so the credential-bearing collector did not need a restart. The dashboard and chart read this admission layer; the raw `predictions` table and CLI statistics remain unfiltered research observations. For admitted results, use the dashboard or CSV admission column. CHECKING setups fail closed until a guard decision exists; BLOCKED setups appear under **Filtered setups** and are excluded from the dashboard’s signal count and win rates.

Records before the saved policy activation timestamp remain BASELINE. Their historical review may say the new policy would have blocked them, but they are not removed or relabeled as successful trades. Displayed summary rates include baseline and approved entries; filter the CSV by admission when comparing the new policy alone. The chart overlays trend SMA200, the last completed M5 EMA50 and confirmed levels. At-entry details distinguish the historical review from the live policy decision.

On the two GBP/USD UP entries at 12:38 and 12:39 Detroit time on September 21, stored prefix-only data showed both trend checks DOWN. The new gate would have blocked both; this is retrospective diagnosis of those examples, not evidence that the new policy improves out-of-sample performance. Prospective observations remain necessary. Strategies designed as reversals will now be admitted only when their reversal direction agrees with the broader trend. The original 5 PM entry cutoff remains unchanged.

### Continuous weekday schedule

To replace the current 5 PM cutoff, stop the collector with Ctrl+C and run this in the same Terminal holding the OANDA demo environment variables:

```sh
caffeinate -i .venv/bin/python -m directional_bot.session --weekdays --resume
```

`--resume` reconstructs indicators from saved candles and continues the same run, preserving signal history and pending outcomes without reissuing historical signals. It requires the prior collector to have stopped cleanly. Duplicate active collectors are rejected. Catch-up candles can resolve saved outcomes, while stale catch-up bars do not generate fresh signals.

Weekday mode allows signals from Monday 00:00 through Friday 23:59:59 in America/Detroit, with timezone-aware daylight-saving handling. It briefly reads final expiry candles at the start of Saturday, then pauses API polling for the weekend and resumes on Monday. The collector process must remain running through the weekend. OANDA market closures, holidays, provider maintenance and network interruptions can still result in stale/missing prices; the bot does not invent candles or interpret unchanged data as fresh data.

The dashboard shows **Monday–Friday / 24 HOURS** only after the active collector has actually switched to this schedule. The trend guard stays active through weekend pauses. Local `caffeinate -i` prevents idle system sleep while the collector runs, but does not guarantee operation with the laptop lid closed, after shutdown/reboot, or without network/power. Keep the Terminal open. This is a local weekday collector, not an installed boot-time service; after reboot, restore environment credentials and rerun the command. No live orders are enabled.

### EUR/USD and AUD/USD focus studies

The dashboard keeps dedicated charts for strategy 01 (EUR/USD, MA Stack + RSI)
and strategy 03 (AUD/USD, MA + Stochastic) above the other monitors. Each has
independent zoom, latest-entry selection, indicators, and entry markers. Charts
and setup summaries refresh every five seconds; candles remain completed M1 bars.

Each focus study compares approved entries at one and three minutes by trend
alignment, five-minute pullback followed by a directional candle, opposing wick
size, and distance to confirmed support/resistance in ATR. Baseline and blocked
counts remain separate. Expand the entry history to inspect both wins and losses
and jump to their chart entries. Pullback calculations require contiguous minute
candles; absent context is excluded rather than inferred. Groups overlap and are
exploratory, not changes to signal admission rules or calibrated probabilities.


### Current assignment: four strategies, two pairs each

New sessions and resumed sessions use this assignment:

| Strategy | Primary pair | Second pair |
|---|---|---|
| 01 MA Stack + RSI | EUR/USD | NZD/USD |
| 02 Multi MA + MACD | GBP/USD | USD/JPY |
| 03 MA + Stochastic | AUD/USD | USD/CHF |
| 08 Oscillator Confluence | USD/SGD | USD/CAD |

Strategies 04–07 are paused for new signals; their saved predictions remain in
SQLite under their original strategy IDs. This assignment supersedes the original
eight-strategy session table above. Each pair keeps separate outcomes, feed status,
trend decisions and chart indicators. The focus charts remain EUR/USD and AUD/USD.
Internal feed IDs stay stable; the dashboard displays the actual assigned strategy.

To activate on an existing collector, press Ctrl+C in its credential-bearing Terminal,
then run `caffeinate -i .venv/bin/python -m directional_bot.session --weekdays --resume`.
Resume records the assignment change and its effective time in the run configuration,
warms indicators from saved history without generating historical entries, and resolves
outstanding outcomes normally. The dashboard reads the persisted active assignment,
so it does not claim the new mapping is live before the collector has restarted.


### Four-panel dashboard

The dashboard groups available feeds by their actual strategy assignment. Each
strategy has one panel with its own pair dropdown, chart, and pair-specific 1m/3m
summary. Additional feeds appear as dropdown options without adding duplicate
panels. Pair selection survives five-second refreshes; panels switch independently.
Charts use completed M1 candles. Entries/outcomes, indicators/rules, and setup
analysis are collapsed by default and remain available within each panel. CSV
exports follow the selected pair. The layout uses two columns on wider screens
and one column on narrow screens. This supersedes the previous dedicated focus
charts and eight-card layout; collection and saved results are unchanged.


### London hourly observation

The dashboard server runs an hourly-note recorder every 30 seconds, reading saved
M1 candles without additional OANDA requests. Its observation window is weekdays
08:00–17:00 Europe/London, with daylight saving handled by the timezone database.
Notes persist in `data/london-hourly.sqlite3` and appear in the dashboard’s collapsed
London hourly notes section. The browser need not stay open, but the dashboard
server and market-data collector must remain running. No restart of the collector
is required. There are no messages or external notifications.

Each pair/hour records observed OHLC, change and range in pips, first/second-half
moves, coverage and admitted 1m/3m outcomes grouped by entry hour. Candle CLOSE
09:00 belongs to 08:00–09:00; a signal entered at 09:00 belongs to the next hour.
Forming, incomplete and fully missing hours are distinguished. Missing candles are
never filled. Pending outcomes are refreshed on subsequent passes. Historical
hours from before recorder activation are explicitly marked historical. The table
shows the latest 144 pair-hour records; older notes remain in SQLite. This is an
observation window definition, not an exchange opening-hours guarantee.


### Live global-session timeline

A 24-hour timeline at the top keeps now centered (12 hours on each side) and
updates every second. London, Aussie/Sydney, Tokyo and New York each have a row;
a separate overlap row highlights simultaneous windows, with names and Detroit
opening/closing times on hover. A status line lists current overlaps and the next
opening/closing countdown. Session definitions use each city's local weekday and
IANA timezone, not fixed UTC offsets: London 08–17, Sydney 08–17, Tokyo 09–18,
New York 08–17. These are indicative FX activity windows, not instrument trading
availability; holidays and broker closures are not encoded. The display's schedule
is independent of the collector and does not alter signals or collection hours.

## September 22 paper trial and activity board

The dashboard now includes all-pair cold/warm/hot activity beneath the session timeline. Strategy 08 uses a versioned rejection-wick and three-minute repeat-entry trial. See the local `analysis/quality-v2/report.md` (not distributed in Git). Historical entries remain unchanged.

## September 22 parallel strategy trial

Strategies 01 and 02 independently observe EUR/USD, NZD/USD, GBP/USD and USD/JPY from 09:41:53 Detroit to midnight tonight. The existing collector supplies candles; the `directional_bot.cross_trial` worker adds only the four complementary strategy/pair combinations. All raw candidates retain exact 1m/3m outcomes and causal trend decisions. Historical candles warm indicators only; stale/missed entries are not recreated as live signals. Current horizon comparisons use the common trial start; earlier observations remain a separate cohort.

The extra evaluator stops entries at the stored end time and settles for four more minutes. Strategies 03/08 and the normal weekday collector continue. Dashboard pair selectors and charts include the extra combinations. The trial settings and heartbeat are in SQLite `cross_trial`; logs are in `data/cross-trial.log`. After a computer restart, resume the normal collector and run `PYTHONPATH=src .venv/bin/python -m directional_bot.cross_trial --db data/dashboard.sqlite3` from this project directory while the trial is active. No broker orders are sent.

The parallel trial expanded at 2026-09-22T13:45:45.875041+00:00: strategies 03 and 08 independently observe AUD/USD, USD/CHF, USD/CAD and USD/SGD until the same midnight deadline. Primary horizons are 3m for 01/02 and 1m for 03/08; both outcomes remain recorded. Hot countdowns use the primary horizon. Strategy 08 retains Quality v2, including its 180-second cooldown, on all four pairs. The second group has its own common start recorded as cross_trial.second_start.

## Collection-first phase

The parallel evaluator now supports `cross_trial.schedule = weekdays`: all 16 strategy/pair combinations continue beyond the original one-day deadline and skip new weekend entries in Detroit time. Both outcomes remain recorded; primary horizons are unchanged. The dashboard and primary collector retain their existing behavior. Local research baseline: `analysis/collection-baseline/frozen-rules.json` (excluded from Git).

Current signal rules are frozen. A daily Codex task reviews the previous completed weekday at 00:10 Detroit, saving local reports under `analysis/daily-review`. This is scheduled research, not a continuously retraining model: candidate changes must be evaluated on later untouched data before adoption. No orders are sent. This computer and the required app/processes must remain available; sleep, shutdown or network failures interrupt collection and can delay scheduled reviews.
