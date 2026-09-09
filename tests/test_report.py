import threading
import unittest
from datetime import date
from types import SimpleNamespace
from unittest.mock import patch

from ohi_o_reg_tracker import report


class ReportTests(unittest.TestCase):
    def test_exports_and_quotas_run_in_parallel(self):
        export_barrier = threading.Barrier(2)
        quota_barrier = threading.Barrier(2)
        event = SimpleNamespace(
            key="test",
            name="Test event",
            event_date=date(2026, 10, 24),
            timezone="America/New_York",
            participant_survey_id="SV_participants",
            participant_quota_id="QO_participants",
            leader_survey_id="SV_leaders",
            leader_quota_id="QO_leaders",
            history=SimpleNamespace(aggregate_output="history.csv", label="2025"),
        )
        settings = SimpleNamespace(base_url="https://example.test", api_key="key", event=event)

        def export(survey_id, **kwargs):
            export_barrier.wait(timeout=2)
            return ["2026-09-01 12:00:00"] if "participants" in survey_id else []

        def quota(survey_id, quota_id, **kwargs):
            quota_barrier.wait(timeout=2)
            return 10 if "participants" in survey_id else 2

        with patch.object(report, "load_aggregate", return_value={}), patch.object(report.qualtrics, "export_end_dates", side_effect=export), patch.object(report.qualtrics, "get_quota_count", side_effect=quota), patch.object(report.charts, "make_chart", return_value=b"png"):
            result = report.build(settings, today=date(2026, 9, 8))

        self.assertEqual((result.participants, result.leaders), (10, 2))


if __name__ == "__main__":
    unittest.main()
