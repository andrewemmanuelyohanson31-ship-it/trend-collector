import unittest

from collect import (DISCOVERY_GEOS, SEEDS, backoff, clean_name, collect_classify, collect_discover, connect,
                     run_requests, save_candidates, todays_pairs)


class TestDiscover(unittest.TestCase):
    def test_noise_filtered_and_upsert_keeps_max(self):
        con = connect(":memory:")
        n = save_candidates(con, "game", "US", [
            ("Krillion Game", 11600), ("vikings game today", 1600), ("nuggets vs celtics", 900),
            ("got sport login", 60),
        ], "t1")
        self.assertEqual(n, 1)
        save_candidates(con, "game", "GB", [("krillion game", 300)], "t2")
        self.assertEqual(
            con.execute("SELECT term, source_geo, rising_value, first_seen, last_seen FROM candidates").fetchall(),
            [("krillion game", "US", 11600, "t1", "t2")],  # source and max value kept, last_seen updated
        )

    def test_discover_continues_after_a_failure(self):
        def fake(seed, geo):
            if seed == "food":
                raise ConnectionError("429")
            return [(f"{seed} thing {geo}", 100)]

        con = connect(":memory:")
        collect_discover(con, fetch=fake, pause=0, pairs=[("US", "food"), ("US", "drink")])
        self.assertEqual([t for (t,) in con.execute("SELECT term FROM candidates")], ["drink thing us"])

    def test_rotation_covers_every_pair(self):
        seen = {p for day in range(4) for p in todays_pairs(day)}
        self.assertEqual(len(todays_pairs(0)), 6)
        self.assertEqual(seen, {(g, s) for g in DISCOVERY_GEOS for s in SEEDS})


class TestClassify(unittest.TestCase):
    def test_clean_name(self):
        self.assertEqual(clean_name("korean beauty glass skin trend", "Glass Skin"), "glass skin")
        self.assertEqual(clean_name("labubu", "labubu"), "labubu")
        self.assertEqual(clean_name("dubai chocolate", "chocolate"), "dubai chocolate")  # too generic
        self.assertEqual(clean_name("spaghett drink", "spaghetti drink"), "spaghett drink")  # invented word
        self.assertEqual(clean_name("x y", ""), "x y")

    def test_classify_only_unlabelled_once(self):
        con = connect(":memory:")
        save_candidates(con, "toy", "US", [("squishy toys collectible trend", 750), ("tovi toy", 500)], "t1")
        asked = []

        def fake(term, seed):
            asked.append(term)
            return "Toy_Collectible ", "squishy toys" if "squishy" in term else term

        collect_classify(con, ask=fake)
        collect_classify(con, ask=fake)  # second run: nothing left to ask
        self.assertEqual(len(asked), 2)
        self.assertEqual(sorted(con.execute("SELECT category, name FROM candidates")),
                         [("toy_collectible", "squishy toys"), ("toy_collectible", "tovi toy")])


class TestRateLimit(unittest.TestCase):
    def test_backoff_retries_429_then_gives_up(self):
        calls, waits = [], []

        def flaky(x):
            calls.append(x)
            if len(calls) < 3:
                raise Exception("Google returned a response with code 429")
            return "ok"

        self.assertEqual(backoff(flaky, waits=(1, 2), sleep=waits.append)("a"), "ok")
        self.assertEqual(waits, [1, 2])

        def always(x):
            raise Exception("code 429")

        with self.assertRaises(Exception):
            backoff(always, waits=(1,), sleep=lambda s: None)("a")

    def test_backoff_does_not_retry_other_errors(self):
        calls = []

        def broken(x):
            calls.append(x)
            raise ValueError("bad keyword")

        with self.assertRaises(ValueError):
            backoff(broken, waits=(1,), sleep=lambda s: None)("a")
        self.assertEqual(len(calls), 1)

    def test_stops_after_failures_in_a_row(self):
        done = []

        def do(x):
            if x != "ok":
                raise ConnectionError("429")
            done.append(x)
            return "fine"

        with self.assertRaises(RuntimeError):
            run_requests("t", [("ok",), ("a",), ("b",), ("c",), ("ok",)], do, pause=0)
        self.assertEqual(done, ["ok"])  # never reached the last job


if __name__ == "__main__":
    unittest.main()
