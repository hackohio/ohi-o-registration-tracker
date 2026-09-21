import tempfile
import unittest
from datetime import date
from pathlib import Path
from ohi_o_reg_tracker.registrations import load_participant_aggregate, timeline

class RegistrationTests(unittest.TestCase):
    def test_cumulative_days_before(self):
        result = timeline(["2026-03-01 12:00:00", "2026-03-03 12:00:00"], date(2026, 3, 7), "America/New_York", today=date(2026, 3, 4))
        self.assertEqual(result, {6: 1, 5: 1, 4: 2, 3: 2})

    def test_future_timestamp_rejected(self):
        with self.assertRaises(ValueError):
            timeline(["2026-03-08 00:00:00"], date(2026, 3, 7), "America/New_York")

    def test_loads_participant_trend(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "trend.csv"
            path.write_text("days_before,participants\n2,1\n1,3\n0,4\n")
            self.assertEqual(load_participant_aggregate(path), {2: 1, 1: 3, 0: 4})

if __name__ == "__main__": unittest.main()
