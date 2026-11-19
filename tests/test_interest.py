import tempfile
import unittest
from pathlib import Path

from collect import collect_interest, connect, load_keywords, save_interest


def rows(con):
    return con.execute("SELECT keyword, date, value FROM interest ORDER BY keyword, date").fetchall()


class TestInterest(unittest.TestCase):
    def test_load_keywords_skips_blanks_comments_dupes(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "k.txt"
            p.write_text("kanzler\n\n# note\nsosis\nkanzler\n  matcha  \n", encoding="utf-8")
            self.assertEqual(load_keywords(p), ["kanzler", "sosis", "matcha"])

    def test_refetch_replaces_not_duplicates(self):
        con = connect(":memory:")
        save_interest(con, "kanzler", [("2026-11-17", 44), ("2026-11-18", 41)], "t1")
        save_interest(con, "kanzler", [("2026-11-17", 50), ("2026-11-18", 47)], "t2")  # Google rescaled
        self.assertEqual(rows(con), [("kanzler", "2026-11-17", 50), ("kanzler", "2026-11-18", 47)])

    def test_one_failing_keyword_does_not_stop_others(self):
        def fake(kw):
            if kw == "bad":
                raise ConnectionError("429")
            return [("2026-11-18", 10)]

        con = connect(":memory:")
        collect_interest(con, ["a", "bad", "b"], fetch=fake, pause=0)
        self.assertEqual([r[0] for r in rows(con)], ["a", "b"])

    def test_all_failing_raises(self):
        def fake(kw):
            raise ConnectionError("429")

        with self.assertRaises(RuntimeError):
            collect_interest(connect(":memory:"), ["a", "b"], fetch=fake, pause=0)


if __name__ == "__main__":
    unittest.main()
