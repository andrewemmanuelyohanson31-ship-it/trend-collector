# CLAUDE.md

Daily collector of Google Trends data for Indonesia → SQLite (`trends.db`) → CSV for data-analyst-agent.
Part of a plan: this feeds project #9 (trend detection). Keep it small; the analysis lives in data-analyst-agent.

## Layout
- `collect.py` — entry point; fetches sources and writes to `trends.db`
- `export.py` — dumps tables to CSV
- `keywords.txt` — tracked keywords, one per line
- `tests/` — stdlib `unittest`, offline (network calls are faked or read from `tests/sample_rss.xml`)

## Rules
- RSS source uses the standard library only. `pytrends` is the only dependency.
- Writes are idempotent: re-running the same day must not duplicate rows (primary keys + INSERT OR IGNORE / REPLACE).
- One failing keyword or source must not abort the run; log it and continue.
- Fetch each keyword alone in pytrends (values are relative to the batch, so batching would make them mixed).
- Run tests with `python -m unittest -v` before committing.
- Commit titles: short, about 6 words.

## Requirements
Python 3.10+, internet, `pip install -r requirements.txt` inside `.venv`.
