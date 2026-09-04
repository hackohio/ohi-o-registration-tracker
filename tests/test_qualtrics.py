import io
import unittest
import zipfile

from ohi_o_reg_tracker.qualtrics import QualtricsError, export_end_dates


class Response:
    def __init__(self, *, data=None, content=b"", status=200):
        self._data, self.content, self.status_code = data, content, status
        self.headers = {}

    def json(self): return self._data
    def raise_for_status(self):
        if self.status_code >= 400: raise RuntimeError(self.status_code)


class Session:
    def __init__(self, responses): self.responses, self.calls = iter(responses), []
    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        return next(self.responses)


class QualtricsTests(unittest.TestCase):
    def test_exports_only_end_date_in_event_timezone(self):
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w") as archive:
            archive.writestr("survey.csv", 'EndDate\nEnd Date\n"{""ImportId"":""endDate"",""timeZone"":""America/New_York""}"\n2026-09-01 12:30:00\n')
        session = Session([
            Response(data={"result": {"progressId": "P1", "status": "inProgress"}}),
            Response(data={"result": {"fileId": "F1", "status": "complete"}}),
            Response(content=output.getvalue()),
        ])

        result = export_end_dates("SV_1", base_url="https://example.test/API/v3", api_key="secret", timezone="America/New_York", session=session)

        self.assertEqual(result, ["2026-09-01 12:30:00"])
        self.assertEqual(session.calls[0][2]["json"], {
            "format": "csv",
            "compress": True,
            "surveyMetadataIds": ["endDate"],
            "questionIds": [],
            "embeddedDataIds": [],
            "timeZone": "America/New_York",
        })
        self.assertTrue(session.calls[2][1].endswith("/F1/file"))

    def test_reports_safe_qualtrics_error_details(self):
        session = Session([Response(status=403, data={
            "meta": {"requestId": "REQ-1", "error": {"errorCode": "AUTH_1", "errorMessage": "Forbidden"}}
        })])
        with self.assertRaisesRegex(QualtricsError, r"HTTP 403.*AUTH_1.*REQ-1"):
            export_end_dates("SV_1", base_url="https://example.test/API/v3", api_key="secret", session=session)


if __name__ == "__main__": unittest.main()
