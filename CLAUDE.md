# CLAUDE.md

Predicts Indonesia's next viral trend: discovers fads rising abroad (US/UK), tracks them abroad and in Indonesia,
scores lead-lag growth. Data → SQLite (`trends.db`) → CSV for data-analyst-agent. Runs daily via Task Scheduler.

## Layout
- `collect.py` — steps in order: trending (RSS, 10 countries) → discover (pytrends rising queries) →
  classify (local Ollama qwen2.5:3b) → interest (12-month weekly, source geo + ID)
- `predict.py` — heuristic score + stage → `predictions.csv`
- `export.py` — all tables to CSV
- `keywords.txt` — reference keywords (known virals), always tracked vs US
- `run.bat` — daily job (collect + predict), logs to `logs/collect.log`
- `tests/` — stdlib `unittest`, offline (network and Ollama faked via injected `fetch`/`ask` functions)

## Rules
- `pytrends` is the only dependency; RSS and Ollama calls use the standard library.
- Writes are idempotent (primary keys + INSERT OR IGNORE / REPLACE / upsert).
- One failing request, keyword, country or step must not abort the run; log it and continue.
- Fetch each keyword alone in pytrends (values are relative to the request, so batching mixes them).
- Keep Google request count low: discovery rotates (`DISCOVER_PER_RUN`), interest refetches only after `REFRESH_DAYS`, one shared pytrends session, backoff on 429 and stop after `MAX_FAILS_IN_ROW`.
- `predict.py` is a heuristic, not a trained model. Don't call it one; once months of data exist, backtest it.
- Run `python -m unittest -v` before committing. Commit titles: short, about 6 words.

## Requirements
Python 3.10+, internet, `pip install -r requirements.txt` in `.venv`, Ollama with `qwen2.5:3b` on localhost:11434.
