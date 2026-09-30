import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from ohi_o_reg_tracker.config import load_events, settings_for


class ConfigTests(unittest.TestCase):
    def _write_config(self, directory, optional_fields=""):
        aggregate = Path(directory) / "history.csv"
        aggregate.write_text("days_before,participants,leaders\n0,10,2\n", encoding="utf-8")
        config = Path(directory) / "events.toml"
        config.write_text(
            """[qualtrics]
base_url = "https://example.test/API/v3"

[events.demo]
name = "Demo"
event_date = 2099-10-24
timezone = "America/New_York"
participant_survey_id = "SV_participants"
leader_survey_id = "SV_leaders"
"""
            + optional_fields
            + """
[events.demo.history]
label = "2025"
event_date = 2025-10-26
participants_input = "private/participants.csv"
leaders_input = "private/leaders.csv"
aggregate_output = """
            + json.dumps(str(aggregate))
            + "\n",
            encoding="utf-8",
        )
        return config

    def test_optional_ids_load_and_validate_together(self):
        with tempfile.TemporaryDirectory() as directory:
            config = self._write_config(directory, """
professional_survey_id = "SV_professionals"
marion_quota_id = "QO_marion"
""")

            _, events = load_events(config)
            settings = settings_for("demo", path=config, require_credentials=False, today=date(2026, 1, 1))

            self.assertEqual(events["demo"].professional_survey_id, "SV_professionals")
            self.assertEqual(settings.event.marion_quota_id, "QO_marion")

    def test_partial_optional_configuration_fails_validation(self):
        with tempfile.TemporaryDirectory() as directory:
            config = self._write_config(directory, 'professional_survey_id = "SV_professionals"\n')

            for participant_only in (False, True):
                with self.subTest(participant_only=participant_only), self.assertRaisesRegex(ValueError, "must be configured together"):
                    settings_for(
                        "demo",
                        path=config,
                        require_credentials=False,
                        today=date(2026, 1, 1),
                        participant_only=participant_only,
                    )

    def test_malformed_optional_id_fails_validation(self):
        with tempfile.TemporaryDirectory() as directory:
            config = self._write_config(directory, """
professional_survey_id = "SV_professionals"
marion_quota_id = "bad-quota"
""")

            with self.assertRaisesRegex(ValueError, "marion_quota_id must be a valid QO_ ID"):
                settings_for("demo", path=config, require_credentials=False, today=date(2026, 1, 1))

    def test_event_without_optional_ids_keeps_existing_configuration(self):
        with tempfile.TemporaryDirectory() as directory:
            config = self._write_config(directory)

            settings = settings_for("demo", path=config, require_credentials=False, today=date(2026, 1, 1))

            self.assertIsNone(settings.event.professional_survey_id)
            self.assertIsNone(settings.event.marion_quota_id)


if __name__ == "__main__":
    unittest.main()
