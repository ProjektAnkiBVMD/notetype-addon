import datetime
import importlib.util
import unittest
from pathlib import Path

_path = Path(__file__).parents[1] / "src/projekt_anki_notetypes/butler/lernplan_calendar.py"
_spec = importlib.util.spec_from_file_location("lernplan_calendar", _path)
cal = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cal)

DAY = datetime.date(2026, 10, 26)
NOW = datetime.datetime(2026, 10, 26, 8, tzinfo=datetime.timezone.utc)


class TestLernplanCalendar(unittest.TestCase):
    def test_events_and_stable_uids(self):
        ics = cal.build_ics([("001", DAY), ("002", DAY + datetime.timedelta(days=1))], {"001": "Herz, Kreislauf"}, DAY, NOW)
        self.assertEqual(ics.count("BEGIN:VEVENT"), 3)
        self.assertIn("UID:lernplan-tag-001@projekt-anki", ics)
        self.assertIn("DTSTART;VALUE=DATE:20261026", ics)
        self.assertIn("Herz\\, Kreislauf", ics)
        self.assertTrue(ics.endswith("END:VCALENDAR\r\n"))

    def test_long_lines_are_folded(self):
        ics = cal.build_ics([("001", DAY)], {"001": "ä" * 100}, None, NOW)
        for line in ics.split("\r\n"):
            self.assertLessEqual(len(line.encode()), 75)
        unfolded = ics.replace("\r\n ", "")
        self.assertIn("ä" * 100, unfolded)


if __name__ == "__main__":
    unittest.main()
