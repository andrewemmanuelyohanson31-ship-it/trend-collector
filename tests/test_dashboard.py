import unittest
from pathlib import Path

from streamlit.testing.v1 import AppTest

from collect import connect, save_interest
from dashboard import keyword_series

APP = str(Path(__file__).parent.parent / "dashboard.py")


class TestDashboard(unittest.TestCase):
    def test_keyword_series_columns(self):
        con = connect(":memory:")
        save_interest(con, "padel", [("2026-01-04", 10), ("2026-01-11", 20)], "t", geo="US")
        save_interest(con, "padel", [("2026-01-04", 0), ("2026-01-11", 5)], "t")
        wide = keyword_series(con, "padel", "US")
        self.assertEqual(list(wide.columns), ["Indonesia", "abroad (US)"])
        self.assertEqual(wide["abroad (US)"].tolist(), [10, 20])

    def test_app_renders_on_real_db(self):
        at = AppTest.from_file(APP, default_timeout=30).run()
        self.assertFalse(at.exception)


if __name__ == "__main__":
    unittest.main()
