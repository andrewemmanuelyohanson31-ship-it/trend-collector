# Trend Collector

Collects Google search trends for Indonesia once a day and stores them in a local SQLite file, so that
later you have the **history** needed to spot what is rising (project #9, "what's about to blow up").
The output feeds into [data-analyst-agent](../data-analyst-agent) as CSV.

Free: no API key, no account, runs on your own PC.

## What it collects

| Source | What | Table |
|---|---|---|
| Google Trends daily RSS (`trends.google.com/trending/rss?geo=ID`) | Today's trending searches in Indonesia, approx. traffic, top news headline | `trending` |
| Google Trends interest over time (via `pytrends`) | 0–100 search interest per day for each keyword in `keywords.txt`, last 3 months | `interest` |

Interest values are **relative to each keyword's own peak** (each keyword is fetched alone). Use them to see whether
one keyword is rising or falling, not to compare two keywords' sizes.

## Requirements

- Windows, macOS or Linux
- Python 3.10+ (tested on 3.12)
- Internet connection
- `pytrends` (only for the `interest` source; the RSS source uses the standard library only)

## Setup

Windows (PowerShell):
```powershell
cd trend-collector
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
```

macOS / Linux:
```bash
cd trend-collector
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Usage

```bash
python collect.py                 # collect everything into trends.db
python collect.py --only trending # just the RSS feed
python collect.py --only interest # just the keywords
python export.py                  # write trending.csv and interest.csv for the data-analyst-agent
```

Edit `keywords.txt` (one keyword per line) to choose what to track.

## Run it every day

The data is only useful if it builds up, so schedule it.

Windows (Task Scheduler, runs daily at 09:00):
```powershell
schtasks /create /tn "TrendCollector" /sc daily /st 09:00 /tr "C:\Users\ikank\trend-collector\run.bat"
```

macOS / Linux (cron):
```bash
0 9 * * * cd /path/to/trend-collector && .venv/bin/python collect.py >> logs/collect.log 2>&1
```

The PC must be on at that time. A missed day just leaves a gap in `trending`; `interest` refills history on the next run.

## Tests

```bash
python -m unittest -v
```

Tests run offline using a saved sample of the RSS feed (`tests/sample_rss.xml`).

## Limits

- `pytrends` is an unofficial, unmaintained library. Google sometimes answers with **HTTP 429 (too many requests)**.
  The collector waits between keywords and skips a keyword that fails, so one failure doesn't stop the run.
- The RSS feed shows only roughly the last day's top searches (about 10–20 items), so daily runs matter.
- Google Trends terms of use apply. This is for personal and academic research.
