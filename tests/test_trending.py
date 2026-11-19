import unittest
from pathlib import Path

from collect import connect, parse_rss, save_trending

SAMPLE = (Path(__file__).parent / "sample_rss.xml").read_bytes()


class TestTrending(unittest.TestCase):
    def test_parse_sample_feed(self):
        rows = parse_rss(SAMPLE)
        self.assertEqual(len(rows), 10)
        first = rows[0]
        self.assertEqual(first["term"], "kabupaten brebes")
        self.assertEqual(first["approx_traffic"], 100)  # "100+" -> 100
        self.assertTrue(first["pub_date"].endswith("+00:00"))  # normalised to UTC
        self.assertTrue(first["news_title"])
        self.assertTrue(all(r["term"] for r in rows))

    def test_save_is_idempotent(self):
        con = connect(":memory:")
        rows = parse_rss(SAMPLE)
        self.assertEqual(save_trending(con, rows, "2026-11-19T00:00:00+00:00"), 10)
        self.assertEqual(save_trending(con, rows, "2026-11-19T01:00:00+00:00"), 0)  # same day re-run
        self.assertEqual(con.execute("SELECT COUNT(*) FROM trending").fetchone()[0], 10)


if __name__ == "__main__":
    unittest.main()
