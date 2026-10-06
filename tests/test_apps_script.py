import json
import unittest
from unittest.mock import patch

import requests

from ohi_o_reg_tracker.apps_script import AppsScriptError, fetch_timestamps


URL = "https://script.google.com/macros/s/DEPLOYMENT/exec"


class Response:
    def __init__(self, status=200, payload=None, headers=None, error=None):
        self.status_code = status
        self.payload = payload
        self.headers = headers or {}
        self.error = error

    def json(self):
        if self.error: raise self.error
        return self.payload

    def iter_content(self, chunk_size):
        if self.error: raise self.error
        yield json.dumps(self.payload).encode()


class Session:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = []

    def post(self, url, **kwargs):
        self.calls.append(("POST", url, kwargs))
        return next(self.responses)

    def get(self, url, **kwargs):
        self.calls.append(("GET", url, kwargs))
        return next(self.responses)


class AppsScriptTests(unittest.TestCase):
    def fetch(self, session, **kwargs):
        return fetch_timestamps(URL, secret="shared-secret", stream="participants",
                                timezone="America/Detroit", session=session, **kwargs)

    def test_success_empty_and_post_body_secret(self):
        for timestamps in ([], ["2026-09-25 13:24:26"]):
            with self.subTest(timestamps=timestamps):
                session = Session([Response(payload={
                    "ok": True, "stream": "participants", "timezone": "America/Detroit",
                    "timestamps": timestamps,
                })])
                self.assertEqual(self.fetch(session), timestamps)
                method, _, kwargs = session.calls[0]
                self.assertEqual(method, "POST")
                self.assertEqual(kwargs["json"], {"secret": "shared-secret", "stream": "participants"})
                self.assertEqual(kwargs["timeout"][0], 5)
                self.assertGreater(kwargs["timeout"][1], 2)
                self.assertNotIn("shared-secret", URL)

    def test_content_service_redirect_uses_secret_free_get(self):
        session = Session([
            Response(302, headers={"Location": "https://script.googleusercontent.com/macros/echo?token=result"}),
            Response(payload={"ok": True, "stream": "participants", "timezone": "America/Detroit", "timestamps": []}),
        ])
        self.assertEqual(self.fetch(session), [])
        self.assertEqual([call[0] for call in session.calls], ["POST", "GET"])
        self.assertEqual(session.calls[1][2].get("json"), None)
        self.assertNotIn("secret", session.calls[1][2])

    def test_unexpected_and_login_redirects_fail_closed(self):
        for location in (
            "https://attacker.example/result",
            "https://accounts.google.com/ServiceLogin",
            "http://script.googleusercontent.com/result",
        ):
            with self.subTest(location=location):
                with self.assertRaisesRegex(AppsScriptError, "redirect"):
                    self.fetch(Session([Response(302, headers={"Location": location})]))

    def test_rejects_unsuccessful_or_malformed_payloads(self):
        responses = [
            Response(payload={"ok": False, "error": "unauthorized"}),
            Response(error=ValueError("login html")),
            Response(payload={"ok": True, "stream": "leaders", "timezone": "America/Detroit", "timestamps": []}),
            Response(payload={"ok": True, "stream": "participants", "timezone": "UTC", "timestamps": []}),
            Response(payload={"ok": True, "stream": "participants", "timezone": "America/Detroit", "timestamps": [], "name": "not allowed"}),
            Response(payload={"ok": True, "stream": "participants", "timezone": "America/Detroit"}),
            Response(payload={"ok": True, "stream": "participants", "timezone": "America/Detroit", "timestamps": ""}),
            Response(payload={"ok": True, "stream": "participants", "timezone": "America/Detroit", "timestamps": ["2026-02-30 12:00:00"]}),
            Response(payload={"ok": True, "stream": "participants", "timezone": "America/Detroit", "timestamps": [None]}),
        ]
        for response in responses:
            with self.subTest(response=response):
                with self.assertRaises(AppsScriptError):
                    self.fetch(Session([response]))

    def test_retries_transient_status_and_transport_error_is_secret_safe(self):
        session = Session([
            Response(503, headers={"Retry-After": "0"}),
            Response(payload={"ok": True, "stream": "participants", "timezone": "America/Detroit", "timestamps": []}),
        ])
        with patch("ohi_o_reg_tracker.apps_script.time.sleep"):
            self.assertEqual(self.fetch(session), [])
        self.assertEqual(len(session.calls), 2)

        class FlakySession:
            attempts = 0
            def post(self, *args, **kwargs):
                self.attempts += 1
                if self.attempts == 1: raise requests.ConnectionError("temporary")
                return Response(payload={"ok": True, "stream": "participants",
                                         "timezone": "America/Detroit", "timestamps": []})
        flaky = FlakySession()
        with patch("ohi_o_reg_tracker.apps_script.time.sleep"):
            self.assertEqual(self.fetch(flaky), [])
        self.assertEqual(flaky.attempts, 2)

        class BrokenSession:
            def post(self, *args, **kwargs):
                raise requests.ConnectionError("shared-secret https://private.example")
        with patch("ohi_o_reg_tracker.apps_script.time.sleep"):
            with self.assertRaises(AppsScriptError) as raised:
                self.fetch(BrokenSession())
        self.assertNotIn("shared-secret", str(raised.exception))
        self.assertNotIn("private.example", str(raised.exception))

    def test_deadline_and_bad_endpoint(self):
        session = Session([Response(payload={
            "ok": True, "stream": "participants", "timezone": "America/Detroit", "timestamps": [],
        })])
        with patch("ohi_o_reg_tracker.apps_script.time.monotonic", side_effect=[0, 0, 61]):
            with self.assertRaisesRegex(AppsScriptError, "deadline"):
                self.fetch(session)
        with self.assertRaisesRegex(AppsScriptError, "URL"):
            fetch_timestamps("https://script.google.com/macros/s/id/exec?secret=x",
                             secret="x", stream="participants", timezone="UTC")


if __name__ == "__main__":
    unittest.main()
