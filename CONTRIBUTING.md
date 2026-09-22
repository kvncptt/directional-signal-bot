# Contributing

Use Python 3.11 or newer. Clone the repository and create an isolated environment:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -e .
.venv/bin/python -m unittest discover -s tests -v
```

Create a branch for each change and open a pull request for review. Keep trading execution disabled. Use synthetic candles and fake OANDA responses in tests. Never commit tokens, account IDs, environment files, databases, logs, or live trading exports. Each contributor uses their own local data and OANDA practice credentials.

The dashboard runs on your own computer. Cloning the source does not share the owner's live dashboard or database. Start a local dashboard with:

```sh
.venv/bin/python -m directional_bot.dashboard --db data/dashboard.sqlite3
```

Then open http://127.0.0.1:8877/. See README for practice-data collection. Private source PDFs and local analysis reports are not distributed in this repository; implemented strategy assumptions are documented in docs/strategy-specifications.md.

The supplemental cross-trial evaluator requires a configured trial in the local database. Do not copy production databases or credentials to enable it. Preserve causal signal generation, exact-time outcome labeling, strategy-version separation and existing records when proposing changes.
