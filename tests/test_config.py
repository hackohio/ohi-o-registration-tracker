import json
import tempfile
import unittest
from datetime import date
from unittest.mock import patch
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

    def _write_sheets_config(self, directory, participant_source, leader_source, *, qualtrics=""):
        aggregate = Path(directory) / "history.csv"
        aggregate.write_text("days_before,participants,leaders\n0,10,2\n", encoding="utf-8")
        config = Path(directory) / "events.toml"
        config.write_text(
            qualtrics
            + '\n[events.demo]\nname = "Demo"\nevent_date = 2099-10-24\ntimezone = "America/Detroit"\n'
            + participant_source + leader_source
            + '\n[events.demo.history]\nlabel = "2025"\nevent_date = 2025-10-26\n'
            + 'participants_input = "private/p.csv"\nleaders_input = "private/l.csv"\n'
            + f"aggregate_output = {json.dumps(str(aggregate))}\n",
            encoding="utf-8",
        )
        return config

    def test_sheets_only_needs_only_its_secret_and_webhook(self):
        with tempfile.TemporaryDirectory() as directory:
            config = self._write_sheets_config(
                directory,
                'participant_apps_script_url = "https://script.google.com/macros/s/p/exec"\n',
                'leader_apps_script_url = "https://script.google.com/macros/s/l/exec"\n',
            )
            with patch.dict("os.environ", {
                "QUALTRICS_API_KEY": "", "GOOGLE_SHEETS_API_SECRET": "sheet-secret",
                "DISCORD_WEBHOOK_URL": "webhook",
            }, clear=False):
                settings = settings_for("demo", path=config, today=date(2026, 1, 1))
            self.assertIsNone(settings.base_url)
            self.assertIsNone(settings.api_key)
            self.assertEqual(settings.sheets_api_secret, "sheet-secret")

    def test_mixed_sources_require_both_provider_credentials(self):
        with tempfile.TemporaryDirectory() as directory:
            config = self._write_sheets_config(
                directory,
                'participant_apps_script_url = "https://script.google.com/macros/s/p/exec"\n',
                'leader_survey_id = "SV_leaders"\n',
                qualtrics='[qualtrics]\nbase_url = "https://example.test/API/v3"\n',
            )
            env = {"QUALTRICS_API_KEY": "q-key", "GOOGLE_SHEETS_API_SECRET": "s-key",
                   "DISCORD_WEBHOOK_URL": "webhook"}
            with patch.dict("os.environ", env, clear=False):
                settings = settings_for("demo", path=config, today=date(2026, 1, 1))
            self.assertEqual(settings.api_key, "q-key")
            self.assertEqual(settings.sheets_api_secret, "s-key")

    def test_missing_ambiguous_and_malformed_sources_fail(self):
        cases = [
            ("", 'leader_survey_id = "SV_leaders"\n', "exactly one"),
            ('participant_survey_id = "SV_p"\nparticipant_apps_script_url = "https://script.google.com/macros/s/p/exec"\n', 'leader_survey_id = "SV_l"\n', "exactly one"),
            ('participant_apps_script_url = "http://script.google.com/macros/s/p/exec"\n', 'leader_survey_id = "SV_l"\n', "HTTPS"),
            ('participant_apps_script_url = "https://user:pass@script.google.com/macros/s/p/exec"\n', 'leader_survey_id = "SV_l"\n', "HTTPS"),
            ('participant_apps_script_url = "https://script.google.com:8443/macros/s/p/exec"\n', 'leader_survey_id = "SV_l"\n', "HTTPS"),
            ('participant_apps_script_url = "https://script.google.com/macros/s/p/exec?x=y"\n', 'leader_survey_id = "SV_l"\n', "HTTPS"),
        ]
        for participant, leader, message in cases:
            with self.subTest(participant=participant), tempfile.TemporaryDirectory() as directory:
                config = self._write_sheets_config(directory, participant, leader)
                with self.assertRaisesRegex(ValueError, message):
                    settings_for("demo", path=config, require_credentials=False, today=date(2026, 1, 1))

    def test_professional_marion_requires_qualtrics_participant(self):
        with tempfile.TemporaryDirectory() as directory:
            config = self._write_sheets_config(
                directory,
                'participant_apps_script_url = "https://script.google.com/macros/s/p/exec"\n',
                'leader_survey_id = "SV_l"\nprofessional_survey_id = "SV_pro"\nmarion_quota_id = "QO_m"\n',
                qualtrics='[qualtrics]\nbase_url = "https://example.test/API/v3"\n',
            )
            with self.assertRaisesRegex(ValueError, "require a Qualtrics participant"):
                settings_for("demo", path=config, require_credentials=False, today=date(2026, 1, 1))

    def test_participant_only_needs_no_leader_or_webhook_credentials(self):
        with tempfile.TemporaryDirectory() as directory:
            config = self._write_sheets_config(
                directory,
                'participant_apps_script_url = "https://script.google.com/macros/s/p/exec"\n',
                "",
            )
            with patch.dict("os.environ", {"GOOGLE_SHEETS_API_SECRET": "sheet-secret",
                                             "DISCORD_WEBHOOK_URL": ""}, clear=False):
                settings = settings_for("demo", path=config, today=date(2026, 1, 1), participant_only=True)
            self.assertIsNone(settings.event.leader_survey_id)
            self.assertEqual(settings.sheets_api_secret, "sheet-secret")

    def test_full_report_requires_source_specific_credentials(self):
        with tempfile.TemporaryDirectory() as directory:
            config = self._write_sheets_config(
                directory,
                'participant_apps_script_url = "https://script.google.com/macros/s/p/exec"\n',
                'leader_survey_id = "SV_leaders"\n',
                qualtrics='[qualtrics]\nbase_url = "https://example.test/API/v3"\n',
            )
            with patch.dict("os.environ", {"GOOGLE_SHEETS_API_SECRET": "",
                                             "QUALTRICS_API_KEY": "", "DISCORD_WEBHOOK_URL": ""}, clear=False):
                with self.assertRaisesRegex(ValueError, "QUALTRICS_API_KEY is missing.*GOOGLE_SHEETS_API_SECRET is missing.*DISCORD_WEBHOOK_URL is missing"):
                    settings_for("demo", path=config, today=date(2026, 1, 1))


if __name__ == "__main__":
    unittest.main()
