import contextlib
import io
import os
import tempfile
import unittest
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from ohi_o_reg_tracker import __main__


def configured_event():
    return SimpleNamespace(
        key="hack",
        name="HackOHI/O",
        event_date=date(2099, 10, 24),
        timezone="America/New_York",
        participant_survey_id="SV_participants",
        professional_survey_id="SV_professionals",
        marion_quota_id="QO_marion",
        leader_survey_id="SV_leaders",
        history=SimpleNamespace(
            aggregate_output="history.csv",
            label="2025",
            participant_trends=(),
        ),
    )


class CliTests(unittest.TestCase):
    def test_dry_run_prints_quota_breakdowns(self):
        event = configured_event()
        settings = SimpleNamespace(event=event)
        result = SimpleNamespace(
            days_before=4,
            event_name="HackOHI/O",
            participants=92,
            historical_participants=76,
            marion=7,
            professionals=12,
            leaders=5,
            historical_leaders=4,
            png=b"png",
        )
        output = io.StringIO()
        with tempfile.TemporaryDirectory() as directory, contextlib.redirect_stdout(output):
            previous = os.getcwd()
            os.chdir(directory)
            try:
                with patch.object(__main__, "load_events", return_value=("", {"hack": event})), \
                        patch.object(__main__, "settings_for", return_value=settings), \
                        patch.object(__main__, "build", return_value=result):
                    self.assertEqual(__main__.main(["report", "--event", "hack", "--dry-run"]), 0)
                self.assertEqual((Path(directory) / "artifacts/hack.png").read_bytes(), b"png")
                self.assertEqual(sorted(path.name for path in (Path(directory) / "artifacts").iterdir()), ["hack.png"])
            finally:
                os.chdir(previous)

        self.assertIn("Participants: 92", output.getvalue())
        self.assertIn("Marion: 7", output.getvalue())
        self.assertIn("Professional: 12", output.getvalue())

    def test_preview_combines_surveys_and_shows_breakdowns(self):
        event = configured_event()
        settings = SimpleNamespace(base_url="https://example.test", api_key="key", event=event)
        output = io.StringIO()
        quota_values = {("SV_participants", "QO_marion"): 7}
        chart_kwargs = {}
        quota_calls = []

        def export(survey_id, **kwargs):
            if survey_id == "SV_participants":
                return ["2026-09-01 12:00:00"]
            if survey_id == "SV_professionals":
                return ["2026-09-02 12:00:00"]
            return []

        def quota(survey_id, quota_id, **kwargs):
            quota_calls.append((survey_id, quota_id))
            return quota_values[(survey_id, quota_id)]

        def chart(current, *args, **kwargs):
            chart_kwargs["current"] = current
            chart_kwargs.update(kwargs)
            return b"png"

        with tempfile.TemporaryDirectory() as directory, contextlib.redirect_stdout(output):
            previous = os.getcwd()
            os.chdir(directory)
            try:
                with patch.object(__main__, "load_events", return_value=("", {"hack": event})), \
                        patch.object(__main__, "settings_for", return_value=settings), \
                        patch.object(__main__, "fetch_timestamps", return_value=["2026-09-01 12:00:00"]) as fetch, \
                        patch.object(__main__.qualtrics, "export_end_dates", side_effect=export), \
                        patch.object(__main__.qualtrics, "get_quota_count", side_effect=quota), \
                        patch.object(__main__, "load_aggregate", return_value={1: (70, 5), 0: (75, 6)}), \
                        patch.object(__main__.charts, "make_chart", side_effect=chart):
                    self.assertEqual(__main__.main(["preview-participants", "--event", "hack"]), 0)
            finally:
                os.chdir(previous)

        self.assertIn("Participants: 2", output.getvalue())
        self.assertIn("Marion: 7", output.getvalue())
        self.assertIn("Professional: 1", output.getvalue())
        self.assertEqual(quota_calls, [("SV_participants", "QO_marion")])
        fetch.assert_called_once_with(settings, "participant")
        self.assertEqual(chart_kwargs["current"][chart_kwargs["today_days_before"]], 2)

    def test_build_history_does_not_need_live_credentials(self):
        with tempfile.TemporaryDirectory() as directory:
            participant_input = Path(directory) / "participants.csv"
            leader_input = Path(directory) / "leaders.csv"
            aggregate_output = Path(directory) / "history.csv"
            participant_input.write_text("EndDate\n2025-10-25 12:00:00\n", encoding="utf-8")
            leader_input.write_text("EndDate\n2025-10-26 12:00:00\n", encoding="utf-8")
            event = SimpleNamespace(
                key="highschool", name="HighSchool", event_date=date(2025, 10, 26),
                timezone="America/Detroit",
                history=SimpleNamespace(event_date=date(2025, 10, 26),
                    participants_input=participant_input, leaders_input=leader_input,
                    aggregate_output=aggregate_output),
            )
            with patch.dict(os.environ, {}, clear=True), \
                    patch.object(__main__, "load_events", return_value=(None, {"highschool": event})):
                self.assertEqual(__main__.main(["build-history", "--event", "highschool"]), 0)
            self.assertEqual(aggregate_output.read_text(encoding="utf-8"),
                "days_before,participants,leaders\n1,1,0\n0,1,1\n")

    def test_required_sheets_failure_prevents_discord_delivery(self):
        event = configured_event()
        event.participant_survey_id = None
        event.participant_apps_script_url = "https://script.google.com/macros/s/p/exec"
        settings = SimpleNamespace(base_url=None, api_key=None, sheets_api_secret="secret", event=event)
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr), \
                patch.object(__main__, "load_events", return_value=(None, {"hack": event})), \
                patch.object(__main__, "settings_for", return_value=settings), \
                patch.object(__main__, "load_aggregate", return_value={}), \
                patch.object(__main__, "fetch_timestamps", side_effect=RuntimeError("source failed")), \
                patch.object(__main__.qualtrics, "export_end_dates", return_value=[]), \
                patch.object(__main__.discord, "send") as send:
            status = __main__.main(["report", "--event", "hack"])
        self.assertEqual(status, 1)
        send.assert_not_called()
        self.assertIn("report failed", stderr.getvalue())

    def test_required_qualtrics_failure_prevents_discord_delivery(self):
        event = configured_event()
        settings = SimpleNamespace(base_url="https://example.test", api_key="key", event=event)

        def export(survey_id, **kwargs):
            if survey_id == "SV_professionals":
                raise RuntimeError("professional export failed")
            return []

        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr), \
                patch.object(__main__, "load_events", return_value=("", {"hack": event})), \
                patch.object(__main__, "settings_for", return_value=settings), \
                patch.object(__main__, "load_aggregate", return_value={}), \
                patch.object(__main__.qualtrics, "export_end_dates", side_effect=export), \
                patch.object(__main__.discord, "send") as send:
            status = __main__.main(["report", "--event", "hack"])

        self.assertEqual(status, 1)
        send.assert_not_called()
        self.assertIn("report failed", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
