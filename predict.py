"""Rank tracked fads by how likely they are to be Indonesia's next big thing. Usage: python predict.py

Heuristic, not a trained model: a fad that is growing abroad and has started growing in Indonesia scores
highest. Writes predictions.csv and prints the ranking.
"""
import csv
import math
import sys
from pathlib import Path

from collect import TARGET, connect, load_keywords, tracked

RECENT = 4  # weeks
BASE = 12  # weeks before RECENT
ID_GROWTH_CAP = 5  # growth from ~0 is huge but meaningless; cap it in the score


def momentum(values):
    """Recent weeks vs the weeks before them; 1.0 = flat, 2.0 = doubled."""
    recent, base = values[-RECENT:], values[-RECENT - BASE:-RECENT]
    if not recent or not base:
        return 1.0
    return (sum(recent) / len(recent) + 1) / (sum(base) / len(base) + 1)  # +1: zero weeks don't divide by 0


def assess(src, idn):
    """(score, stage, growth abroad, growth in Indonesia) from weekly 0-100 series."""
    src_m, id_m = momentum(src), momentum(idn)
    id_now = sum(idn[-RECENT:]) / RECENT if len(idn) >= RECENT else 0
    window = idn[-RECENT - BASE:]
    # Few searches: Google scales each series to its own peak, so 2 searches after months of 0 read as "100"
    sparse = window.count(0) > len(window) / 2
    if not any(window):
        stage = "growing abroad, not in Indonesia yet" if src_m >= 1.3 else "not in Indonesia"
        score = 0.5 * math.log(src_m)
    elif sparse and sum(1 for v in idn[-RECENT:] if v) >= 3:
        stage = "first signs in Indonesia"  # searched most recent weeks after a quiet stretch
        score = 0.5 * math.log(src_m) + math.log(min(id_m, ID_GROWTH_CAP))
    elif sparse:
        stage = "too few searches in Indonesia"
        score = 0.5 * math.log(src_m)
    else:
        score = 0.5 * math.log(src_m) + math.log(min(id_m, ID_GROWTH_CAP))
        if id_m >= 1.5:
            stage = "rising in Indonesia"
        elif id_now >= 60 and id_m < 0.9:
            stage = "peaked in Indonesia"
        elif id_now >= 60:
            stage = "big in Indonesia now"
        else:
            stage = "flat"
    return round(score, 3), stage, round(src_m, 2), round(id_m, 2)


def series(con, keyword, geo):
    return [v for (v,) in con.execute(
        "SELECT value FROM interest WHERE keyword = ? AND geo = ? AND value IS NOT NULL ORDER BY date", (keyword, geo))]


def fetched(con, keyword, geo):
    return con.execute("SELECT 1 FROM interest WHERE keyword = ? AND geo = ?", (keyword, geo)).fetchone() is not None


def predict(con, pairs):
    out = []
    for kw, src in pairs:
        s, i = series(con, kw, src), series(con, kw, TARGET)
        if not s or not fetched(con, kw, TARGET):
            continue  # not fetched yet
        i = i or [0] * len(s)  # fetched, but Google had no Indonesian data at all
        score, stage, src_m, id_m = assess(s, i)
        out.append({"keyword": kw, "source": src, "stage": stage, "score": score,
                    "growth_abroad": src_m, "growth_indonesia": id_m})
    return sorted(out, key=lambda r: r["score"], reverse=True)


if __name__ == "__main__":
    con = connect()
    rows = predict(con, tracked(con, load_keywords()))
    if not rows:
        sys.exit("no interest data yet - run collect.py first")
    with open(Path(__file__).parent / "predictions.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=rows[0])
        w.writeheader()
        w.writerows(rows)
    for r in rows:
        print(f"{r['score']:+.2f}  {r['keyword']:35s} {r['stage']:38s} abroad x{r['growth_abroad']}  ID x{r['growth_indonesia']}")
