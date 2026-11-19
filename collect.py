"""Collect trend data into trends.db. Usage: python collect.py [--only trending|discover|classify|interest]

trending  - today's trending searches (RSS) in Indonesia and source countries
discover  - "rising" searches abroad for broad seed topics -> candidates (the auto starting keywords)
classify  - local Ollama model labels each new candidate and names the fad ("glass skin", "squishy toys")
interest  - 12 months of weekly interest for tracked fads, in the source country AND in Indonesia
"""
import argparse
import functools
import json
import re
import sqlite3
import sys
import time
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

HERE = Path(__file__).parent
DB_PATH = HERE / "trends.db"
TARGET = "ID"
RSS_GEOS = [TARGET, "US", "GB", "AU", "SG", "MY", "PH", "KR", "JP", "TH"]
DISCOVERY_GEOS = ["US", "GB"]  # where fads usually show up first, in English
SEEDS = ["food", "drink", "snack", "toy", "game", "sport", "hobby", "fashion", "app", "trend"]
DISCOVER_PER_RUN = 6  # of the 20 geo/seed pairs; rotates daily so all are covered every 4 days
TREND_CATEGORIES = {"food_drink", "toy_collectible", "game", "sport_hobby", "beauty_fashion", "gadget_app"}
TRACK_LIMIT = 15  # auto candidates tracked; each costs 2 Google requests per refresh
TRACK_DAYS = 30  # keep tracking a candidate this long after it was last seen rising
MAX_NAME_WORDS = 3  # longer names are one-off phrases nobody in Indonesia will search
REFRESH_DAYS = 6  # interest is weekly data; refetching it daily only burns rate limit
PAUSE = 10  # seconds between Google requests
MAX_FAILS_IN_ROW = 3  # Google is blocking us; stop the step and try again next run
OLLAMA_URL = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "qwen2.5:3b"
HT = "{https://trends.google.com/trending/rss}"
NOISE = re.compile(r"\b(vs|today|tonight|score|scores|login|near me|open on|schedule|channel)\b", re.I)

SCHEMA = """
CREATE TABLE IF NOT EXISTS trending (
    geo TEXT, term TEXT, pub_date TEXT, approx_traffic INTEGER,
    news_title TEXT, news_source TEXT, fetched_at TEXT,
    PRIMARY KEY (geo, term, pub_date)
);
CREATE TABLE IF NOT EXISTS candidates (
    term TEXT PRIMARY KEY, source_geo TEXT, seed TEXT, rising_value INTEGER,
    first_seen TEXT, last_seen TEXT, category TEXT, name TEXT
);
CREATE TABLE IF NOT EXISTS interest (
    geo TEXT, keyword TEXT, date TEXT, value INTEGER, fetched_at TEXT,
    PRIMARY KEY (geo, keyword, date)
);
"""


def connect(path=DB_PATH):
    con = sqlite3.connect(path)
    con.executescript(SCHEMA)
    if "name" not in {r[1] for r in con.execute("PRAGMA table_info(candidates)")}:
        con.execute("ALTER TABLE candidates ADD COLUMN name TEXT")  # databases created before names existed
    return con


def now_utc():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@functools.cache
def trend_req():
    from pytrends.request import TrendReq  # imported here so RSS and tests work without pytrends

    return TrendReq(hl="en-US", tz=-420)  # one session: each new one costs an extra cookie request


def backoff(fn, waits=(60, 120), sleep=time.sleep):
    """Retry fn on HTTP 429 after each wait in `waits`, then give up."""
    @functools.wraps(fn)
    def wrapped(*args):
        for wait in (*waits, None):
            try:
                return fn(*args)
            except Exception as e:
                if wait is None or "429" not in str(e):
                    raise
                print(f"  429, waiting {wait}s", file=sys.stderr)
                sleep(wait)
    return wrapped


def run_requests(label, jobs, do, pause=PAUSE):
    """Run do(*job) for each job with a pause between; skip failures, stop after MAX_FAILS_IN_ROW."""
    failures = in_row = 0
    for i, job in enumerate(jobs):
        if i:
            time.sleep(pause)
        try:
            print(f"{label} {' '.join(map(str, job))}: {do(*job)}")
            in_row = 0
        except Exception as e:  # one request failing must not stop the rest
            print(f"{label} {' '.join(map(str, job))}: FAILED - {e}", file=sys.stderr)
            failures += 1
            in_row += 1
            if in_row >= MAX_FAILS_IN_ROW:
                raise RuntimeError(f"{in_row} failures in a row, stopping {label} until next run")
    if jobs and failures == len(jobs):
        raise RuntimeError(f"all {len(jobs)} {label} requests failed")


# ---- trending (RSS) ----

def parse_rss(xml_text):
    """Return trending rows (dicts) from the Google Trends RSS feed."""
    rows = []
    for item in ET.fromstring(xml_text).iter("item"):
        news = item.find(f"{HT}news_item")
        traffic = (item.findtext(f"{HT}approx_traffic") or "").replace("+", "").replace(",", "")
        rows.append({
            "term": item.findtext("title", "").strip(),
            "pub_date": parsedate_to_datetime(item.findtext("pubDate")).astimezone(timezone.utc).isoformat(),
            "approx_traffic": int(traffic) if traffic.isdigit() else None,
            "news_title": news.findtext(f"{HT}news_item_title") if news is not None else None,
            "news_source": news.findtext(f"{HT}news_item_source") if news is not None else None,
        })
    return rows


def save_trending(con, rows, fetched_at, geo=TARGET):
    """Insert rows, ignoring ones already stored. Returns how many were new."""
    before = con.total_changes
    con.executemany(
        "INSERT OR IGNORE INTO trending VALUES "
        "(:geo, :term, :pub_date, :approx_traffic, :news_title, :news_source, :fetched_at)",
        [{**r, "geo": geo, "fetched_at": fetched_at} for r in rows],
    )
    con.commit()
    return con.total_changes - before


def fetch_rss(geo):
    url = f"https://trends.google.com/trending/rss?geo={geo}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return parse_rss(resp.read())


def collect_trending(con, fetch=fetch_rss):
    for geo in RSS_GEOS:
        try:
            rows = fetch(geo)
            print(f"trending {geo}: {len(rows)} fetched, {save_trending(con, rows, now_utc(), geo)} new")
        except Exception as e:  # one country failing must not stop the rest
            print(f"trending {geo}: FAILED - {e}", file=sys.stderr)


# ---- discover (rising searches abroad) ----

@backoff
def fetch_rising(seed, geo):
    """Return [(query, rising %)] for searches rising around `seed` in the last 3 months."""
    pt = trend_req()
    pt.build_payload([seed], timeframe="today 3-m", geo=geo)
    df = pt.related_queries()[seed]["rising"]
    return [] if df is None else list(zip(df["query"], df["value"].astype(int)))


def save_candidates(con, seed, geo, rising, seen_at):
    """Upsert rising queries as candidates, skipping obvious sports/login noise. Returns how many were kept."""
    kept = [(q.strip().lower(), int(v)) for q, v in rising if not NOISE.search(q)]
    con.executemany(
        """INSERT INTO candidates (term, source_geo, seed, rising_value, first_seen, last_seen)
           VALUES (?, ?, ?, ?, ?, ?)
           ON CONFLICT(term) DO UPDATE SET last_seen = excluded.last_seen,
               rising_value = MAX(rising_value, excluded.rising_value)""",
        [(q, geo, seed, v, seen_at, seen_at) for q, v in kept],
    )
    con.commit()
    return len(kept)


def todays_pairs(day=None, per_run=DISCOVER_PER_RUN):
    pairs = [(geo, seed) for geo in DISCOVERY_GEOS for seed in SEEDS]
    start = ((day if day is not None else datetime.now().toordinal()) * per_run) % len(pairs)
    return [pairs[(start + i) % len(pairs)] for i in range(min(per_run, len(pairs)))]


def collect_discover(con, fetch=fetch_rising, pause=PAUSE, pairs=None):
    def do(geo, seed):
        return f"{save_candidates(con, seed, geo, fetch(seed, geo), now_utc())} kept"

    run_requests("discover", pairs if pairs is not None else todays_pairs(), do, pause)


# ---- classify (local LLM) ----

PROMPT = """Classify this Google search term and name the thing it is about.
Term: "{term}"
It was found as a fast-rising search related to "{seed}".
Categories:
- food_drink: a food, drink, snack or recipe
- toy_collectible: a toy, plush, figure or collectible
- game: a video, board, card or mobile game
- sport_hobby: a sport to play, an activity, a hobby or a craft
- beauty_fashion: a beauty, skincare, hair, nail or clothing style
- gadget_app: a gadget, device or app
- retail_promo: a specific store's sale, product release, seasonal item, advent calendar or recipe change
- sports_match: a professional sports match, team, league or score
- person: a celebrity, athlete, politician or other person
- news_event: news, politics, a lawsuit, a recall, a warning, a study, a show or a one-off event
- other: store hours, logins, definitions, cars, anything else
"name": the short generic name (1-3 words) people anywhere would search for this thing, without years,
store names, "trend", "ideas" or "new". Examples: "pink dragon fruit latte recipe ideas" -> "dragon fruit latte",
"crochet tote bag trend 2025" -> "crochet tote bag", "stanley cup" -> "stanley cup".
Reply as JSON: {{"category": "...", "name": "..."}}"""


def ask_ollama(term, seed):
    body = json.dumps({
        "model": OLLAMA_MODEL, "prompt": PROMPT.format(term=term, seed=seed),
        "format": "json", "stream": False, "options": {"temperature": 0},
    }).encode()
    with urllib.request.urlopen(urllib.request.Request(OLLAMA_URL, body), timeout=120) as resp:
        answer = json.loads(json.loads(resp.read())["response"])
    return answer.get("category", "other"), answer.get("name", "")


def clean_name(term, name):
    """Trust the model's short name only if it is made of the term's own words and isn't over-generic."""
    words, term_words = str(name).lower().split(), term.split()
    if words and set(words) <= set(term_words) and (len(words) >= 2 or words == term_words):
        return " ".join(words)
    return term  # e.g. "dubai chocolate" -> "chocolate" (too generic), "spaghett" -> "spaghetti" (invented)


def collect_classify(con, ask=ask_ollama):
    todo = con.execute("SELECT term, seed FROM candidates WHERE category IS NULL").fetchall()
    for term, seed in todo:
        category, name = ask(term, seed)  # an unreachable Ollama raises; the rest is retried next run
        con.execute("UPDATE candidates SET category = ?, name = ? WHERE term = ?",
                    (str(category).strip().lower(), clean_name(term, name), term))
        con.commit()
    print(f"classify: {len(todo)} labelled")


# ---- interest (source country vs Indonesia) ----

def load_keywords(path=HERE / "keywords.txt"):
    lines = (l.strip() for l in path.read_text(encoding="utf-8").splitlines())
    return list(dict.fromkeys(l.lower() for l in lines if l and not l.startswith("#")))


def tracked(con, keywords, limit=TRACK_LIMIT, today=None):
    """[(keyword, source_geo)]: reference keywords (vs US) + top recent fads by their short name."""
    since = ((today or datetime.now(timezone.utc)) - timedelta(days=TRACK_DAYS)).isoformat()
    cats = sorted(TREND_CATEGORIES)
    rows = con.execute(
        f"""SELECT COALESCE(name, term), source_geo FROM candidates
            WHERE category IN ({','.join('?' * len(cats))}) AND last_seen >= ?
            ORDER BY rising_value DESC""",
        [*cats, since],
    ).fetchall()
    pairs = {k: "US" for k in keywords}
    for name, geo in rows:
        if len(pairs) >= len(keywords) + limit:
            break
        if len(name.split()) <= MAX_NAME_WORDS:
            pairs.setdefault(name, geo)
    return list(pairs.items())


@backoff
def fetch_interest(keyword, geo):
    """Return [(week 'YYYY-MM-DD', value)] for the last 12 months, complete weeks only."""
    pt = trend_req()
    pt.build_payload([keyword], timeframe="today 12-m", geo=geo)  # alone, so values are relative to its own peak
    df = pt.interest_over_time()
    if df.empty:
        return []
    df = df[~df["isPartial"]]  # the current partial week would look like a fake dip
    return [(d.strftime("%Y-%m-%d"), int(v)) for d, v in df[keyword].items()]


def save_interest(con, keyword, points, fetched_at, geo=TARGET):
    # REPLACE: Google rescales the whole series on every fetch, so keep the newest consistent copy
    con.executemany(
        "INSERT OR REPLACE INTO interest VALUES (?, ?, ?, ?, ?)",
        [(geo, keyword, d, v, fetched_at) for d, v in points],
    )
    if not points:  # remember "no data" too, so it isn't refetched every day
        con.execute("INSERT OR REPLACE INTO interest VALUES (?, ?, '', NULL, ?)", (geo, keyword, fetched_at))
    con.commit()


def is_fresh(con, keyword, geo, now=None):
    (last,) = con.execute("SELECT MAX(fetched_at) FROM interest WHERE keyword = ? AND geo = ?", (keyword, geo)).fetchone()
    cutoff = ((now or datetime.now(timezone.utc)) - timedelta(days=REFRESH_DAYS)).isoformat()
    return last is not None and last >= cutoff


def collect_interest(con, pairs=None, fetch=fetch_interest, pause=PAUSE):
    pairs = pairs if pairs is not None else tracked(con, load_keywords())
    jobs = [(kw, geo) for kw, src in pairs for geo in dict.fromkeys([src, TARGET]) if not is_fresh(con, kw, geo)]

    def do(kw, geo):
        points = fetch(kw, geo)
        save_interest(con, kw, points, now_utc(), geo)
        return f"{len(points)} weeks"

    print(f"interest: {len(jobs)} to fetch, {len(pairs) * 2 - len(jobs)} still fresh")
    run_requests("interest", jobs, do, pause)


SOURCES = {
    "trending": collect_trending,
    "discover": collect_discover,
    "classify": collect_classify,
    "interest": collect_interest,
}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", choices=SOURCES)
    args = ap.parse_args(argv)
    con = connect()
    failed = False
    for name, fn in SOURCES.items():
        if args.only and name != args.only:
            continue
        try:
            fn(con)
        except Exception as e:  # one source failing must not stop the others
            print(f"{name}: FAILED - {e}", file=sys.stderr)
            failed = True
        sys.stdout.flush()
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
