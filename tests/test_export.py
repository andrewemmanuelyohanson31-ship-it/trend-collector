import csv
import tempfile
import unittest
from pathlib import Path

from collect import connect, save_interest
from export import export


class TestExport(unittest.TestCase):
    def test_writes_header_and_rows(self):
        con = connect(":memory:")
        save_interest(con, "kanzler", [("2026-11-17", 44), ("2026-11-18", 41)], "t1")
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(export(con, d), {"trending": 0, "candidates": 0, "interest": 2})
            with open(Path(d) / "interest.csv", encoding="utf-8") as f:
                got = list(csv.reader(f))
            self.assertEqual(got[0], ["geo", "keyword", "date", "value", "fetched_at"])
            self.assertEqual(got[1], ["ID", "kanzler", "2026-11-17", "44", "t1"])
            with open(Path(d) / "trending.csv", encoding="utf-8") as f:
                self.assertEqual(len(list(csv.reader(f))), 1)  # header only


if __name__ == "__main__":
    unittest.main()
