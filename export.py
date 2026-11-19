"""Write each table in trends.db to <table>.csv (for data-analyst-agent). Usage: python export.py [out_dir]"""
import csv
import sys
from pathlib import Path

from collect import connect

TABLES = {"trending": "pub_date, term", "interest": "keyword, date"}


def export(con, out_dir):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    counts = {}
    for table, order in TABLES.items():
        cur = con.execute(f"SELECT * FROM {table} ORDER BY {order}")
        rows = cur.fetchall()
        with open(out_dir / f"{table}.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(c[0] for c in cur.description)
            w.writerows(rows)
        counts[table] = len(rows)
    return counts


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else Path(__file__).parent
    for table, n in export(connect(), out).items():
        print(f"{table}.csv: {n} rows")
