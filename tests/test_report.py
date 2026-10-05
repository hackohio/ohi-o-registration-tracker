import threading
import unittest
from datetime import date
from types import SimpleNamespace
from unittest.mock import ANY, patch

from ohi_o_reg_tracker import report


class ReportTests(unittest.TestCase):
    def test_exports_run_in_parallel_and_supply_current_counts(self):
        export_barrier = threading.Barrier(2)
        event = SimpleNamespace(
            key="test",
            name="Test event",
            event_date=date(2026, 10, 24),
            timezone="America/New_York",
            participant_survey_id="SV_participants",
            leader_survey_id="SV_leaders",
            history=SimpleNamespace(aggregate_output="history.csv", label="2025"),
        )
        settings = SimpleNamespace(base_url="https://example.test", api_key="key", event=event)

        def export(survey_id, **kwargs):
            export_barrier.wait(timeout=2)
            return ["2026-09-01 12:00:00"] if "participants" in survey_id else []

        with patch.object(report, "load_aggregate", return_value={}), \
                patch.object(report.qualtrics, "export_end_dates", side_effect=export), \
                patch.object(report.qualtrics, "get_quota_count") as quota, \
                patch.object(report.charts, "make_chart", return_value=b"png"):
            result = report.build(settings, today=date(2026, 9, 8))

        self.assertEqual((result.participants, result.leaders), (1, 0))
        quota.assert_not_called()

    def test_combines_timelines_and_queries_only_marion_quota(self):
        event = SimpleNamespace(
            key="hack",
            name="HackOHI/O",
            event_date=date(2026, 10, 24),
            timezone="America/New_York",
            participant_survey_id="SV_participants",
            professional_survey_id="SV_professionals",
            marion_quota_id="QO_marion",
            leader_survey_id="SV_leaders",
            history=SimpleNamespace(aggregate_output="history.csv", label="2025"),
        )
        settings = SimpleNamespace(base_url="https://example.test", api_key="key", event=event)
        exports = {
            "SV_participants": ["2026-10-01 12:00:00"],
            "SV_professionals": ["2026-10-02 12:00:00", "2026-10-20 12:00:00"],
            "SV_leaders": ["2026-10-03 12:00:00"] * 5,
        }
        quota_values = {
            ("SV_participants", "QO_marion"): 7,
        }
        quota_calls = []
        chart_args = {}

        def export(survey_id, **kwargs):
            return exports[survey_id]

        def quota(survey_id, quota_id, **kwargs):
            quota_calls.append((survey_id, quota_id))
            return quota_values[(survey_id, quota_id)]

        def chart(participants, leaders, historical, **kwargs):
            chart_args.update(participants=participants, leaders=leaders, historical=historical, **kwargs)
            return b"png"

        history = {4: (70, 3), 3: (72, 4), 2: (74, 4), 1: (75, 4), 0: (76, 5)}
        with patch.object(report, "load_aggregate", return_value=history), \
                patch.object(report.qualtrics, "export_end_dates", side_effect=export), \
                patch.object(report.qualtrics, "get_quota_count", side_effect=quota), \
                patch.object(report.charts, "make_chart", side_effect=chart):
            result = report.build(settings, today=date(2026, 10, 20), session=object())

        self.assertEqual((result.participants, result.professionals, result.marion, result.leaders), (3, 2, 7, 5))
        self.assertEqual(quota_calls, [
            ("SV_participants", "QO_marion"),
        ])
        self.assertEqual(chart_args["participants"], {
            23: 1, 22: 2, 21: 2, 20: 2, 19: 2, 18: 2, 17: 2, 16: 2,
            15: 2, 14: 2, 13: 2, 12: 2, 11: 2, 10: 2, 9: 2, 8: 2,
            7: 2, 6: 2, 5: 2, 4: 3,
        })
        self.assertEqual(chart_args["historical"], history)

    def test_mixed_provider_streams_use_the_selected_source(self):
        event = SimpleNamespace(
            key="mixed", name="Mixed event", event_date=date(2026, 10, 24),
            timezone="America/Detroit", participant_survey_id=None,
            participant_apps_script_url="https://script.google.com/macros/s/p/exec",
            leader_survey_id="SV_leaders", history=SimpleNamespace(aggregate_output="history.csv", label="2025"),
        )
        settings = SimpleNamespace(base_url="https://example.test", api_key="q-key",
                                   sheets_api_secret="s-key", event=event)
        with patch.object(report, "load_aggregate", return_value={}), \
                patch.object(report.apps_script, "fetch_timestamps", return_value=["2026-09-01 12:00:00"]) as sheets, \
                patch.object(report.qualtrics, "export_end_dates", return_value=["2026-09-02 12:00:00"]) as qualtrics, \
                patch.object(report.charts, "make_chart", return_value=b"png"):
            result = report.build(settings, today=date(2026, 9, 8), session=object())
        self.assertEqual((result.participants, result.leaders), (1, 1))
        sheets.assert_called_once_with(
            event.participant_apps_script_url, secret="s-key", stream="participants",
            timezone="America/Detroit", session=ANY,
        )
        qualtrics.assert_called_once()

    def test_both_sheets_streams_are_counted(self):
        event = SimpleNamespace(
            key="sheets", name="Sheets event", event_date=date(2026, 10, 24),
            timezone="America/Detroit", participant_survey_id=None, leader_survey_id=None,
            participant_apps_script_url="https://script.google.com/macros/s/p/exec",
            leader_apps_script_url="https://script.google.com/macros/s/l/exec",
            history=SimpleNamespace(aggregate_output="history.csv", label="2025"),
        )
        settings = SimpleNamespace(sheets_api_secret="s-key", event=event)
        def fetch(url, *, stream, **kwargs):
            return ["2026-09-01 12:00:00"] * (2 if stream == "participants" else 3)
        with patch.object(report, "load_aggregate", return_value={}), \
                patch.object(report.apps_script, "fetch_timestamps", side_effect=fetch) as sheets, \
                patch.object(report.charts, "make_chart", return_value=b"png"):
            result = report.build(settings, today=date(2026, 9, 8), session=object())
        self.assertEqual((result.participants, result.leaders), (2, 3))
        self.assertEqual([call.kwargs["stream"] for call in sheets.call_args_list], ["participants", "leaders"])

    def test_professional_timeline_is_kept_when_participant_export_is_empty(self):
        event = SimpleNamespace(
            key="hack",
            name="HackOHI/O",
            event_date=date(2026, 10, 24),
            timezone="America/New_York",
            participant_survey_id="SV_participants",
            professional_survey_id="SV_professionals",
            marion_quota_id="QO_marion",
            leader_survey_id="SV_leaders",
            history=SimpleNamespace(aggregate_output="history.csv", label="2025"),
        )
        settings = SimpleNamespace(base_url="https://example.test", api_key="key", event=event)
        chart_args = {}

        def export(survey_id, **kwargs):
            return [] if survey_id == "SV_participants" else [
                "2026-10-23 12:00:00",
                "2026-10-24 12:00:00",
            ] if survey_id == "SV_professionals" else []

        def chart(participants, leaders, historical, **kwargs):
            chart_args["participants"] = participants
            return b"png"

        with patch.object(report, "load_aggregate", return_value={0: (0, 0)}), \
                patch.object(report.qualtrics, "export_end_dates", side_effect=export), \
                patch.object(report.qualtrics, "get_quota_count", return_value=0), \
                patch.object(report.charts, "make_chart", side_effect=chart):
            report.build(settings, today=date(2026, 10, 24), session=object())

        self.assertEqual(chart_args["participants"], {1: 1, 0: 2})


if __name__ == "__main__":
    unittest.main()
