import unittest
from datetime import date
from ohi_o_reg_tracker.registrations import timeline

class RegistrationTests(unittest.TestCase):
    def test_cumulative_days_before(self):
        result = timeline(["2026-03-01 12:00:00", "2026-03-03 12:00:00"], date(2026, 3, 7), "America/New_York", today=date(2026, 3, 4))
        self.assertEqual(result, {6: 1, 5: 1, 4: 2, 3: 2})

    def test_future_timestamp_rejected(self):
        with self.assertRaises(ValueError):
            timeline(["2026-03-08 00:00:00"], date(2026, 3, 7), "America/New_York")

if __name__ == "__main__": unittest.main()
