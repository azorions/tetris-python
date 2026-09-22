"""Save files: high-score tables and settings, round trips and bad input."""
import contextlib
import io
import json
import os
import tempfile
import unittest

from tetris import storage
from tetris.screens import Settings
from tetris.storage import HighScores


class TempHome(unittest.TestCase):
    """Points TETRIS_HOME at a throwaway folder so tests never touch the real ~/.tetris."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._old = os.environ.get("TETRIS_HOME")
        os.environ["TETRIS_HOME"] = self._tmp.name

    def tearDown(self):
        if self._old is None:
            os.environ.pop("TETRIS_HOME", None)
        else:
            os.environ["TETRIS_HOME"] = self._old
        self._tmp.cleanup()

    def write(self, name, text):
        with open(os.path.join(self._tmp.name, name), "w", encoding="utf-8") as f:
            f.write(text)


class HighScoresTest(TempHome):
    def test_starts_empty(self):
        scores = HighScores.load()
        self.assertEqual(scores.tables, {"marathon": [], "sprint": [], "ultra": []})

    def test_round_trip(self):
        scores = HighScores()
        scores.add("marathon", "ABC", 1200)
        scores.add("sprint", "XYZ", 83456)
        self.assertTrue(scores.save())
        again = HighScores.load()
        self.assertEqual(again.table("marathon"), [("ABC", 1200)])
        self.assertEqual(again.table("sprint"), [("XYZ", 83456)])

    def test_ordering_and_top_five(self):
        scores = HighScores()
        for i, value in enumerate([300, 900, 100, 500, 700, 200]):
            scores.add("marathon", "AAA", value)
            scores.add("sprint", "AAA", value)
        self.assertEqual([v for _, v in scores.table("marathon")], [900, 700, 500, 300, 200])
        self.assertEqual([v for _, v in scores.table("sprint")], [100, 200, 300, 500, 700])

    def test_ties_keep_the_older_entry_first(self):
        scores = HighScores()
        scores.add("ultra", "OLD", 500)
        scores.add("ultra", "NEW", 500)
        self.assertEqual(scores.table("ultra")[0][0], "OLD")

    def test_qualifying(self):
        scores = HighScores()
        self.assertFalse(scores.qualifies("marathon", None))
        self.assertTrue(scores.qualifies("marathon", 1))           # room in the table
        for value in (500, 400, 300, 200, 100):
            scores.add("marathon", "AAA", value)
            scores.add("sprint", "AAA", value)
        self.assertFalse(scores.qualifies("marathon", 100))        # ties don't push anyone out
        self.assertTrue(scores.qualifies("marathon", 101))
        self.assertFalse(scores.qualifies("sprint", 500))
        self.assertTrue(scores.qualifies("sprint", 499))           # faster than the slowest time

    def test_table_is_updated_in_place(self):
        scores = HighScores()
        live = scores.table("marathon")
        scores.add("marathon", "AAA", 10)
        self.assertEqual(live, [("AAA", 10)])

    def test_corrupt_file_gives_empty_tables(self):
        self.write(storage.SCORES_FILE, "{not json")
        self.assertEqual(HighScores.load().table("marathon"), [])
        self.write(storage.SCORES_FILE, "[1, 2, 3]")
        self.assertEqual(HighScores.load().table("marathon"), [])

    def test_bad_entries_are_dropped(self):
        self.write(storage.SCORES_FILE, json.dumps({
            "marathon": [["abc", 100], ["TOOLONG", 5], ["AB1", 5], ["OK", True], ["NEG", -4],
                         ["FLT", 1.5], ["ONE"], "junk", ["ZED", 50]],
            "bogus": [["AAA", 1]],
            "sprint": "not a list",
        }))
        scores = HighScores.load()
        self.assertEqual(scores.table("marathon"), [("ABC", 100), ("ZED", 50)])
        self.assertEqual(scores.table("sprint"), [])
        self.assertNotIn("bogus", scores.tables)

    def test_save_failure_is_reported_not_raised(self):
        blocker = os.path.join(self._tmp.name, "file")
        with open(blocker, "w") as f:
            f.write("x")
        os.environ["TETRIS_HOME"] = os.path.join(blocker, "sub")   # a folder can't live inside a file
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            self.assertFalse(HighScores().save())
        self.assertIn("could not save", err.getvalue())


class SettingsTest(TempHome):
    def test_round_trip(self):
        s = Settings()
        s.shake, s.scanlines, s.start_level, s.music = 0.5, 0, 7, 0.0
        self.assertTrue(storage.save_settings(s.to_dict()))
        t = Settings()
        t.load(storage.load_settings())
        self.assertEqual(t.to_dict(), s.to_dict())

    def test_invalid_values_are_ignored(self):
        s = Settings()
        s.load({"ghost": 1, "shake": 0.25, "start_level": 99, "scanlines": "66", "bogus": 3, "sfx": 0.5})
        self.assertIs(s.ghost, True)                # 1 is not a bool
        self.assertEqual((s.shake, s.start_level, s.scanlines, s.sfx), (1.0, 1, 66, 0.5))

    def test_missing_or_corrupt_file_keeps_defaults(self):
        self.assertEqual(storage.load_settings(), {})
        self.write(storage.SETTINGS_FILE, "[]")
        self.assertEqual(storage.load_settings(), {})

    def test_cycle_wraps(self):
        s = Settings()
        s.cycle(1, -1)                              # SCREEN SHAKE: FULL -> OFF
        self.assertEqual(s.shake, 0.0)
        self.assertEqual(dict(s.rows())["SCREEN SHAKE"], "OFF")


if __name__ == "__main__":
    unittest.main()
