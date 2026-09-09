import json
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace

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
            "**__12__ Days Before Test event**",
            "- **Participants**: 42 (_last year: 37_)",
            "- **Mentor/Judge**: 18 (_last year: 15_)",
        ]))
        self.assertNotIn("embeds", payload)
        self.assertEqual(request["files"]["file"], ("registration.png", b"png", "image/png"))


if __name__ == "__main__": unittest.main()
