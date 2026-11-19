import unittest

from collect import connect, save_interest
from predict import assess, momentum, predict

FLAT = [20] * 52
GROWING = [5] * 40 + [10, 10, 10, 10, 20, 20, 20, 20, 40, 50, 60, 70]


class TestPredict(unittest.TestCase):
    def test_momentum(self):
        self.assertAlmostEqual(momentum(FLAT), 1.0)
        self.assertGreater(momentum(GROWING), 2)
        self.assertEqual(momentum([1, 2]), 1.0)  # too short to judge

    def test_stages(self):
        self.assertEqual(assess(GROWING, [0] * 52)[1], "growing abroad, not in Indonesia yet")
        self.assertEqual(assess(FLAT, [0] * 52)[1], "not in Indonesia")
        self.assertEqual(assess(GROWING, GROWING)[1], "rising in Indonesia")
        self.assertEqual(assess(FLAT, [10] * 36 + [100] * 12 + [70] * 4)[1], "peaked in Indonesia")
        self.assertEqual(assess(FLAT, [80] * 52)[1], "big in Indonesia now")
        self.assertEqual(assess(FLAT, FLAT)[1], "flat")

    def test_sparse_indonesian_series(self):
        # real shapes from 2026-11-19: krillion game (4 weeks in a row) vs hobby horse (1 week)
        self.assertEqual(assess(GROWING, [0] * 48 + [35, 46, 40, 74])[1], "first signs in Indonesia")
        self.assertEqual(assess(GROWING, [0] * 51 + [100])[1], "too few searches in Indonesia")
        self.assertEqual(assess(GROWING, [0] * 50 + [60, 100])[1], "too few searches in Indonesia")
        # a jump from zero must not outscore a fad with real, steady growth abroad and at home
        self.assertLess(assess(FLAT, [0] * 48 + [35, 46, 40, 74])[0], assess(GROWING, GROWING)[0])

    def test_rising_in_indonesia_ranks_first(self):
        con = connect(":memory:")
        weeks = [f"2026-{1 + i // 4:02d}-{1 + i % 4 * 7:02d}" for i in range(52)]
        for kw, src, idn in [("a", FLAT, FLAT), ("b", GROWING, GROWING), ("c", GROWING, [0] * 52)]:
            save_interest(con, kw, list(zip(weeks, src)), "t", "US")
            save_interest(con, kw, list(zip(weeks, idn)), "t", "ID")
        save_interest(con, "nodata", list(zip(weeks, GROWING)), "t", "US")
        save_interest(con, "nodata", [], "t", "ID")  # Google had nothing for Indonesia
        got = predict(con, [("a", "US"), ("b", "US"), ("c", "US"), ("nodata", "US"), ("missing", "US")])
        self.assertEqual([r["keyword"] for r in got][0], "b")
        self.assertEqual({r["keyword"] for r in got}, {"a", "b", "c", "nodata"})  # never fetched: skipped
        self.assertEqual(next(r for r in got if r["keyword"] == "nodata")["stage"],
                         "growing abroad, not in Indonesia yet")


if __name__ == "__main__":
    unittest.main()
