# Trend Collector

Spots what could become **Indonesia's next viral thing** (think padel, mahjong, matcha) by watching what is
rising abroad first, then checking whether Indonesia is starting to follow.

Runs every day on your own PC, stores everything in a local SQLite file, and builds up history over time.
Free: no API key, no account. Feeds into [data-analyst-agent](../data-analyst-agent) as CSV.

## How it works

```
1 discover   rising searches in the US & UK around 10 seed topics (food, drink, toy, game, sport, ...)
     │        e.g. "krillion game", "korean beauty glass skin trend"   → these are the auto starting keywords
     │        (6 of the 20 country/seed pairs per day, rotating: all covered every 4 days)
2 classify   local Ollama model (qwen2.5:3b) labels each term and names the fad:
     │        "korean beauty glass skin trend" → beauty_fashion, "glass skin"
     │        fads kept: food_drink, toy_collectible, game, sport_hobby, beauty_fashion, gadget_app
     │        dropped: retail_promo, sports_match, person, news_event, other
3 interest   12 months of weekly search interest for each fad name, in the source country AND Indonesia
     │        (refetched once it is 6+ days old — it's weekly data)
4 predict    growth abroad vs growth in Indonesia → score + stage → predictions.csv
```

Plus, separately: the daily trending searches (RSS) of Indonesia and 9 other countries are saved every run, for
later analysis.

### Stages

| Stage | Meaning |
|---|---|
| **rising in Indonesia** | Indonesian interest grew 1.5×+ in the last 4 weeks vs the 12 before. The strongest "next big thing" signal. |
| **growing abroad, not in Indonesia yet** | Growing 1.3×+ in the source country, no Indonesian searches yet. Watch list. |
| **big in Indonesia now** | Already near its 12-month peak in Indonesia. |
| **peaked in Indonesia** | Was big, now falling. |
| flat / not in Indonesia | Nothing happening. |

`score = 0.5·ln(growth abroad) + ln(growth in Indonesia)`. Higher = more likely to be next.

**This is a heuristic, not a trained model.** There is no labelled history of "fads that made it" yet. Once a few
months of data have built up, the score can be checked against what actually took off, and tuned or replaced
by a trained model.

### Reference keywords

`keywords.txt` holds known recent virals (padel, mahjong, pickleball, labubu, matcha). They're always tracked,
so you can see what a real boom looks like next to the auto-discovered candidates. Add or remove lines freely.

## Requirements

- Windows, macOS or Linux; Python 3.10+ (tested on 3.12); internet
- `pytrends` (`pip install -r requirements.txt`)
- [Ollama](https://ollama.com) running locally with `qwen2.5:3b` (`ollama pull qwen2.5:3b`) for the classify step.
  If Ollama is off, classify fails, the rest still runs, and the unlabelled terms are labelled on the next run.

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
python collect.py                  # all steps (usually 5-15 min; ~6 discovery + new/stale interest requests)
python collect.py --only discover  # or: trending, classify, interest
python predict.py                  # rank fads -> predictions.csv
python export.py                   # all tables -> trending.csv, candidates.csv, interest.csv
```

## Run it every day

Windows (Task Scheduler, daily at 09:00; runs collect + predict, logs to `logs/collect.log`):
```powershell
schtasks /create /tn "TrendCollector" /sc daily /st 09:00 /tr "C:\Users\ikank\trend-collector\run.bat"
```

macOS / Linux (cron):
```bash
0 9 * * * cd /path/to/trend-collector && .venv/bin/python collect.py && .venv/bin/python predict.py >> logs/collect.log 2>&1
```

The PC must be on (and Ollama running) at that time. Missed days leave gaps in `trending` and `candidates`;
`interest` refills its 12 months on the next run.

## Data (trends.db)

| Table | Columns |
|---|---|
| `trending` | geo, term, pub_date, approx_traffic, news_title, news_source, fetched_at |
| `candidates` | term, source_geo, seed, rising_value (% growth Google reports), first_seen, last_seen, category, name (short fad name that gets tracked) |
| `interest` | geo, keyword, date (week), value (0-100, relative to that keyword's own peak in that country), fetched_at |

Each keyword is fetched alone, so values show whether **one** keyword is rising, not how two compare in size.

## Tests

```bash
python -m unittest -v
```

Offline: network and Ollama calls are faked; the RSS test reads a saved feed (`tests/sample_rss.xml`).

## Limits

- `pytrends` is unofficial and unmaintained. Google rate-limits with **HTTP 429** after roughly 20 quick
  requests. The collector waits 60 s then 120 s and retries; after 3 failures in a row it stops that step
  until the next run. So the first days fill in gradually, not all at once.
- The classifier is a 3B model: it misses things it has never heard of and lets some noise through. The
  growth data is the real judge, the classifier only keeps the list short.
- Only the top 15 fresh candidates are tracked per run (each costs 2 requests).
- Google Trends terms of use apply. For personal and academic research.
