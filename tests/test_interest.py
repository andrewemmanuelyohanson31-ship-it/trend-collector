import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from collect import collect_interest, connect, is_fresh, load_keywords, save_candidates, save_interest, tracked

NOW = datetime(2026, 11, 19, tzinfo=timezone.utc)


def rows(con):
    return con.execute("SELECT geo, keyword, date, value FROM interest ORDER BY keyword, geo, date").fetchall()


class TestInterest(unittest.TestCase):
    def test_load_keywords_skips_blanks_comments_dupes(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "k.txt"
            p.write_text("padel\n\n# note\nMahjong\npadel\n  matcha  \n", encoding="utf-8")
            self.assertEqual(load_keywords(p), ["padel", "mahjong", "matcha"])

    def test_refetch_replaces_not_duplicates(self):
        con = connect(":memory:")
        save_interest(con, "padel", [("2026-11-08", 44), ("2026-11-15", 41)], "t1")
        save_interest(con, "padel", [("2026-11-08", 50), ("2026-11-15", 47)], "t2")  # Google rescaled
        self.assertEqual(rows(con), [("ID", "padel", "2026-11-08", 50), ("ID", "padel", "2026-11-15", 47)])

    def test_fetches_source_country_and_indonesia(self):
        calls = []

        def fake(kw, geo):
            calls.append((kw, geo))
            return [("2026-11-15", 10)]

        collect_interest(connect(":memory:"), [("padel", "US"), ("x", "GB")], fetch=fake, pause=0)
        self.assertEqual(calls, [("padel", "US"), ("padel", "ID"), ("x", "GB"), ("x", "ID")])

    def test_fresh_data_is_not_refetched(self):
        con = connect(":memory:")
        save_interest(con, "padel", [("2026-11-15", 10)], "2026-11-17T00:00:00+00:00", "US")
        save_interest(con, "padel", [], "2026-11-01T00:00:00+00:00", "ID")  # "no data" also counts, but is old
        self.assertTrue(is_fresh(con, "padel", "US", now=NOW))
        self.assertFalse(is_fresh(con, "padel", "ID", now=NOW))
        self.assertFalse(is_fresh(con, "never", "US", now=NOW))

    def test_one_failing_request_does_not_stop_others(self):
        def fake(kw, geo):
            if kw == "bad":
                raise ConnectionError("429")
            return [("2026-11-15", 10)]

        con = connect(":memory:")
        collect_interest(con, [("a", "US"), ("bad", "US"), ("b", "US")], fetch=fake, pause=0)
        self.assertEqual(sorted({r[1] for r in rows(con)}), ["a", "b"])

    def test_all_failing_raises(self):
        def fake(kw, geo):
            raise ConnectionError("429")

        with self.assertRaises(RuntimeError):
            collect_interest(connect(":memory:"), [("a", "US")], fetch=fake, pause=0)


class TestTracked(unittest.TestCase):
    def test_reference_keywords_then_recent_fads_by_name(self):
        con = connect(":memory:")
        recent, old = "2026-11-18T00:00:00+00:00", "2026-09-01T00:00:00+00:00"
        save_candidates(con, "toy", "US", [("old toy", 9000)], old)
        save_candidates(con, "trend", "US", [("korean beauty glass skin trend", 8000), ("glass skin routine", 100)], recent)
        save_candidates(con, "drink", "GB", [("spaghett drink", 50), ("some lawsuit", 5000),
                                             ("little debbie new breakfast snack", 4000)], recent)
        con.executemany("UPDATE candidates SET category = ?, name = ? WHERE term = ?", [
            ("toy_collectible", "old toy", "old toy"),
            ("beauty_fashion", "glass skin", "korean beauty glass skin trend"),
            ("beauty_fashion", "glass skin", "glass skin routine"),
            ("food_drink", "spaghett drink", "spaghett drink"),
            ("news_event", "some lawsuit", "some lawsuit"),
            ("food_drink", "little debbie new breakfast snack", "little debbie new breakfast snack"),
        ])
        got = tracked(con, ["padel"], today=NOW)
        # old: not seen for 30+ days; lawsuit: not a fad; long name: skipped; glass skin: only once
        self.assertEqual(got, [("padel", "US"), ("glass skin", "US"), ("spaghett drink", "GB")])

    def test_limit(self):
        con = connect(":memory:")
        save_candidates(con, "toy", "US", [(f"toy {i}", i) for i in range(10)], "2026-11-18T00:00:00+00:00")
        con.execute("UPDATE candidates SET category = 'toy_collectible'")
        self.assertEqual(len(tracked(con, ["padel"], limit=3, today=NOW)), 4)


if __name__ == "__main__":
    unittest.main()
