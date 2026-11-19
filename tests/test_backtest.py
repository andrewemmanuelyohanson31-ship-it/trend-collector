import unittest

from backtest import WINDOW, replay, rescale, summarize


class TestBacktest(unittest.TestCase):
    def test_rescale_to_own_peak(self):
        self.assertEqual(rescale([0, 5, 10]), [0, 50, 100])
        self.assertEqual(rescale([0, 0]), [0, 0])

    def test_replay_uses_only_past_data(self):
        # a boom in week 70: the stage before it must not depend on it
        flat = [10] * 100
        boom = [10] * 69 + [100] * 31
        dates = [f"w{i:03d}" for i in range(100)]
        a, b = replay(dates, flat, flat), replay(dates, flat, boom)
        self.assertEqual(len(a), 100 - WINDOW + 1)
        self.assertEqual(a[:69 - WINDOW + 1], b[:69 - WINDOW + 1])  # identical until the boom starts

    def test_signal_before_peak_and_lead_time(self):
        src = [20] * 60 + [40] * 40
        idn = [5] * 60 + [10, 15, 20, 30, 40, 55, 70, 85, 100] + [60] * 31  # grows, peaks at week 68, fades
        dates = [f"w{i:03d}" for i in range(100)]
        peak, first, lead = summarize(dates, idn, replay(dates, src, idn))
        self.assertEqual(peak, "w068")
        self.assertEqual(first[1], "rising in Indonesia")
        self.assertGreater(lead, 0)


if __name__ == "__main__":
    unittest.main()
