import json
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace

import requests

from ohi_o_reg_tracker.discord import send


class Response:
    status_code = 204

    def raise_for_status(self): pass


class Session:
    def __init__(self): self.calls = []

    def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return Response()


class DiscordTests(unittest.TestCase):
    def test_sends_markdown_content_and_chart_attachment(self):
        session = Session()
        report = SimpleNamespace(
            event_name="Test event",
            days_before=12,
            participants=42,
            historical_participants=37,
            leaders=18,
            historical_leaders=15,
            updated_at=datetime(2026, 3, 1, 12, tzinfo=timezone.utc),
            png=b"png",
        )

        send(report, "https://discord.test/webhook", session=session)

        _, request = session.calls[0]
        payload = json.loads(request["data"]["payload_json"])
        self.assertEqual(payload["content"], "\n".join([
            "────────────────",
            "**__12__ Days Before Test event**",
            "- **Participants**: 42 (_last year: 37_)",
            "- **Mentor/Judge**: 18 (_last year: 15_)",
            "────────────────",
        ]))
        self.assertNotIn("embeds", payload)
        self.assertEqual(request["files"]["file"], ("registration.png", b"png", "image/png"))

    def test_appends_count_breakdown_to_same_message_and_attachment(self):
        session = Session()
        report = SimpleNamespace(
            event_name="HackOHI/O",
            days_before=4,
            participants=92,
            historical_participants=76,
            leaders=5,
            historical_leaders=4,
            updated_at=datetime(2026, 10, 20, 12, tzinfo=timezone.utc),
            png=b"png",
            marion=7,
            professionals=12,
        )

        send(report, "https://discord.test/webhook", session=session)

        self.assertEqual(len(session.calls), 1)
        _, request = session.calls[0]
        payload = json.loads(request["data"]["payload_json"])
        self.assertEqual(payload["content"].splitlines()[-1], "-# Marion: 7 | Professional: 12")
        self.assertEqual(request["files"], {"file": ("registration.png", b"png", "image/png")})

    def test_delivery_errors_do_not_include_the_webhook_url(self):
        class FailingSession:
            def post(self, url, **kwargs):
                raise requests.ConnectionError(f"failed to connect to {url}")

        webhook_url = "https://discord.test/webhook/secret"
        report = SimpleNamespace(
            event_name="Test event",
            days_before=1,
            participants=2,
            historical_participants=1,
            leaders=0,
            historical_leaders=0,
            png=b"png",
        )

        with self.assertRaisesRegex(RuntimeError, "Discord delivery failed") as raised:
            send(report, webhook_url, session=FailingSession())

        self.assertNotIn(webhook_url, str(raised.exception))


if __name__ == "__main__": unittest.main()
