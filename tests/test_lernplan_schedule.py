import datetime
import importlib.util
import unittest
from pathlib import Path

# loaded by path: the butler package pulls in aqt, which this test does not need
_path = Path(__file__).parents[1] / "src/projekt_anki_notetypes/butler/lernplan_schedule.py"
_spec = importlib.util.spec_from_file_location("lernplan_schedule", _path)
sched = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sched)

MON = datetime.date(2026, 10, 26)
WORKDAYS = [True] * 5 + [False] * 2


class TestLernplanSchedule(unittest.TestCase):
    def test_remaining_skips_finished_and_respects_order(self):
        order = ["003", "001", "002", "004"]
        self.assertEqual(sched.remaining_lerntage(order, "001", {"004"}), ["001", "002"])
        self.assertEqual(sched.remaining_lerntage(order, "999", set()), ["999", "003", "001", "002", "004"])

    def test_weekends_are_skipped(self):
        fri = MON + datetime.timedelta(days=4)
        result = sched.compute_schedule(["1", "2", "3"], fri, WORKDAYS)
        self.assertEqual([d for _, d in result], [fri, fri + datetime.timedelta(days=3), fri + datetime.timedelta(days=4)])

    def test_skip_and_extra_days(self):
        tue, sat = MON + datetime.timedelta(days=1), MON + datetime.timedelta(days=5)
        result = sched.compute_schedule(["1", "2", "3"], MON, WORKDAYS, extra_days={sat}, skip_days={tue})
        self.assertEqual([d.weekday() for _, d in result], [0, 2, 3])
        result = sched.compute_schedule(["1", "2", "3", "4", "5", "6"], MON, WORKDAYS, extra_days={sat})
        self.assertIn(sat, [d for _, d in result])

    def test_only_extra_days(self):
        days = {MON + datetime.timedelta(days=n) for n in (1, 3)}
        none = [False] * 7
        self.assertEqual(len(sched.compute_schedule(["1", "2", "3"], MON, none, days)), 3)
        self.assertIsNone(sched.compute_schedule(["1", "2", "3", "4"], MON, none, days))
        self.assertIsNone(sched.compute_schedule(["1"], MON, none))

    def test_finish_date(self):
        self.assertEqual(sched.finish_date([], MON), MON)
        self.assertIsNone(sched.finish_date(None, MON))

    def test_parse_dates_ignores_garbage(self):
        self.assertEqual(sched.parse_dates(["2026-10-26", "x", None]), {MON})


if __name__ == "__main__":
    unittest.main()
