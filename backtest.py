"""Check the predictor against trends that already happened. Usage: python backtest.py [keyword ...]

Fetches 5 years of weekly interest (source country + Indonesia) into the `history` table, then replays
predict.assess week by week using only what was known at that time: the previous 52 weeks, rescaled to their own
peak like a live 12-month fetch. Reports when the predictor first said "rising"/"first signs" vs when Indonesia peaked.
"""
import sys
import time

from collect import PAUSE, TARGET, backoff, connect, load_keywords, now_utc, trend_req
from predict import assess

WINDOW = 52
SIGNALS = {"rising in Indonesia", "first signs in Indonesia"}

HISTORY = """CREATE TABLE IF NOT EXISTS history (
    geo TEXT, keyword TEXT, date TEXT, value INTEGER, fetched_at TEXT, PRIMARY KEY (geo, keyword, date))"""


@backoff
def fetch_history(keyword, geo):
    pt = trend_req()
    pt.build_payload([keyword], timeframe="today 5-y", geo=geo)
    df = pt.interest_over_time()
    if df.empty:
        return []
    df = df[~df["isPartial"]]
    return [(d.strftime("%Y-%m-%d"), int(v)) for d, v in df[keyword].items()]


def load(con, keyword, geo):
    return con.execute("SELECT date, value FROM history WHERE keyword = ? AND geo = ? ORDER BY date",
                       (keyword, geo)).fetchall()


def rescale(values):
    peak = max(values)
    return [round(v * 100 / peak) if peak else 0 for v in values]


def replay(dates, src, idn):
    """[(date, stage)] for each week once a full window exists, using only data up to that week."""
    out = []
    for t in range(WINDOW, len(idn) + 1):
        _, stage, _, _ = assess(rescale(src[t - WINDOW:t]), rescale(idn[t - WINDOW:t]))
        out.append((dates[t - 1], stage))
    return out


def summarize(dates, idn, timeline):
    """First signal before Indonesia's all-time peak, and how many weeks early it came."""
    peak_i = max(range(len(idn)), key=idn.__getitem__)
    peak = dates[peak_i]
    first = next(((d, s) for d, s in timeline if s in SIGNALS and d <= peak), None)
    lead = None if first is None else peak_i - dates.index(first[0])
    return peak, first, lead


def main(keywords):
    con = connect()
    con.execute(HISTORY)
    for i, kw in enumerate(keywords):
        for geo in ("US", TARGET):
            if load(con, kw, geo):
                continue  # already fetched; delete rows from `history` to refetch
            if i or geo != "US":
                time.sleep(PAUSE)
            points = fetch_history(kw, geo)
            con.executemany("INSERT OR REPLACE INTO history VALUES (?, ?, ?, ?, ?)",
                            [(geo, kw, d, v, now_utc()) for d, v in points])
            con.commit()
            print(f"fetched {geo} {kw!r}: {len(points)} weeks")
    print()
    for kw in keywords:
        us, idn = dict(load(con, kw, "US")), dict(load(con, kw, TARGET))
        dates = sorted(set(us) & set(idn))
        if len(dates) <= WINDOW:
            print(f"{kw}: not enough history")
            continue
        s, i = [us[d] for d in dates], [idn[d] for d in dates]
        timeline = replay(dates, s, i)
        peak, first, lead = summarize(dates, i, timeline)
        changes = [(d, st) for k, (d, st) in enumerate(timeline) if k == 0 or st != timeline[k - 1][1]]
        verdict = (f"first signal {first[1]!r} on {first[0]}, {lead} weeks before the peak" if first
                   else "NO signal before the peak")
        print(f"{kw}: Indonesia peaked {peak}; {verdict}")
        print("   stage changes: " + "; ".join(f"{d} {st}" for d, st in changes[-8:]))


if __name__ == "__main__":
    main([k.lower() for k in sys.argv[1:]] or load_keywords())
