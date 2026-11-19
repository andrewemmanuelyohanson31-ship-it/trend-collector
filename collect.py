"""Collect Google Trends data for Indonesia into trends.db. Usage: python collect.py [--only trending|interest]"""
import argparse
import sqlite3
import sys
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

HERE = Path(__file__).parent
DB_PATH = HERE / "trends.db"
GEO = "ID"
RSS_URL = f"https://trends.google.com/trending/rss?geo={GEO}"
HT = "{https://trends.google.com/trending/rss}"

SCHEMA = """
CREATE TABLE IF NOT EXISTS trending (
    geo TEXT, term TEXT, pub_date TEXT, approx_traffic INTEGER,
    news_title TEXT, news_source TEXT, fetched_at TEXT,
    PRIMARY KEY (geo, term, pub_date)
);
CREATE TABLE IF NOT EXISTS interest (
    geo TEXT, keyword TEXT, date TEXT, value INTEGER, fetched_at TEXT,
    PRIMARY KEY (geo, keyword, date)
);
"""


def connect(path=DB_PATH):
    con = sqlite3.connect(path)
    con.executescript(SCHEMA)
    return con


def now_utc():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


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


def save_trending(con, rows, fetched_at):
    """Insert rows, ignoring ones already stored. Returns how many were new."""
    before = con.total_changes
    con.executemany(
        "INSERT OR IGNORE INTO trending VALUES "
        "(:geo, :term, :pub_date, :approx_traffic, :news_title, :news_source, :fetched_at)",
        [{**r, "geo": GEO, "fetched_at": fetched_at} for r in rows],
    )
    con.commit()
    return con.total_changes - before


def collect_trending(con):
    req = urllib.request.Request(RSS_URL, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        rows = parse_rss(resp.read())
    new = save_trending(con, rows, now_utc())
    print(f"trending: {len(rows)} fetched, {new} new")


def load_keywords(path=HERE / "keywords.txt"):
    lines = (l.strip() for l in path.read_text(encoding="utf-8").splitlines())
    return list(dict.fromkeys(l for l in lines if l and not l.startswith("#")))


def fetch_interest(keyword):
    """Return [(date 'YYYY-MM-DD', value)] for the last 3 months, complete days only."""
    from pytrends.request import TrendReq  # imported here so the RSS source works without pytrends

    pt = TrendReq(hl="id-ID", tz=-420)  # tz is minutes *behind* UTC; WIB is UTC+7
    pt.build_payload([keyword], timeframe="today 3-m", geo=GEO)  # alone, so values are relative to its own peak
    df = pt.interest_over_time()
    if df.empty:
        return []
    df = df[~df["isPartial"]]  # today's partial value would look like a fake dip
    return [(d.strftime("%Y-%m-%d"), int(v)) for d, v in df[keyword].items()]


def save_interest(con, keyword, points, fetched_at):
    # REPLACE: Google rescales the whole series on every fetch, so keep the newest consistent copy
    con.executemany(
        "INSERT OR REPLACE INTO interest VALUES (?, ?, ?, ?, ?)",
        [(GEO, keyword, d, v, fetched_at) for d, v in points],
    )
    con.commit()


def collect_interest(con, keywords=None, fetch=fetch_interest, pause=10):
    import time

    keywords = keywords if keywords is not None else load_keywords()
    failures = []
    for i, kw in enumerate(keywords):
        if i:
            time.sleep(pause)  # shortcut: fixed delay against 429s; add backoff if they become frequent
        try:
            points = fetch(kw)
            save_interest(con, kw, points, now_utc())
            print(f"interest: {kw!r} {len(points)} days")
        except Exception as e:  # one keyword failing must not stop the rest
            print(f"interest: {kw!r} FAILED - {e}", file=sys.stderr)
            failures.append(kw)
    if failures and len(failures) == len(keywords):
        raise RuntimeError(f"all {len(keywords)} keywords failed")


SOURCES = {"trending": collect_trending, "interest": collect_interest}


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
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
