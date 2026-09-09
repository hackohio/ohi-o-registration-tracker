import csv, io, json, logging, time, zipfile
import requests

logger = logging.getLogger(__name__)

class QualtricsError(RuntimeError): pass

def _raise_for_status(response):
    if response.status_code < 400: return
    try:
        body = response.json()
        error = body.get("meta", {}).get("error") or body.get("error") or {}
        details = ": ".join(str(v) for v in (error.get("errorCode") or error.get("code"), error.get("errorMessage") or error.get("message")) if v)
        request_id = body.get("meta", {}).get("requestId")
    except (ValueError, AttributeError):
        details = request_id = None
    suffix = f" ({details})" if details else ""
    if request_id: suffix += f" [requestId: {request_id}]"
    raise QualtricsError(f"Qualtrics HTTP {response.status_code}{suffix}")

def _json(response):
    _raise_for_status(response)
    try: return response.json()
    except (ValueError, json.JSONDecodeError) as e: raise QualtricsError("Qualtrics returned invalid JSON") from e

def _request(session, method, url, **kwargs):
    for attempt in range(3):
        response = session.request(method, url, **kwargs)
        if response.status_code not in (429, 500, 502, 503, 504): return response
        if attempt == 2: return response
        retry = response.headers.get("Retry-After", "1")
        try: delay = min(float(retry), 30)
        except ValueError: delay = 1
        time.sleep(max(delay, 0.1))
    return response

def export_end_dates(survey_id, *, base_url, api_key, timezone="UTC", session=None, poll_interval=1, deadline=120):
    logger.info("Starting Qualtrics response export")
    session = session or requests.Session(); headers = {"X-API-TOKEN": api_key, "Accept": "application/json"}
    root = base_url.rstrip("/") + f"/surveys/{survey_id}/export-responses"
    body = {"format": "csv", "compress": True, "surveyMetadataIds": ["endDate"], "questionIds": [], "embeddedDataIds": [], "timeZone": timezone}
    response = _request(session, "POST", root, headers=headers, json=body, timeout=(10, 30))
    data = _json(response).get("result", {})
    progress_id = data.get("progressId")
    if not progress_id or data.get("status") not in ("inProgress", "complete"):
        raise QualtricsError("export response lacks valid progressId/status")
    deadline_at = time.monotonic() + deadline
    last_log = 0
    while True:
        if time.monotonic() >= deadline_at: raise QualtricsError("Qualtrics export deadline expired")
        response = _request(session, "GET", root + "/" + progress_id, headers=headers, timeout=(10, 30))
        result = _json(response).get("result", {})
        status = result.get("status")
        if status == "complete":
            logger.info("Qualtrics response export completed")
            file_id = result.get("fileId")
            if not file_id: raise QualtricsError("completed export lacks fileId")
            break
        if status == "failed": raise QualtricsError("Qualtrics export failed")
        if status != "inProgress": raise QualtricsError("export progress lacks valid status")
        now = time.monotonic()
        if now - last_log >= 10:
            logger.info("Waiting for Qualtrics response export (%.0fs remaining)", max(0, deadline_at - now))
            last_log = now
        time.sleep(min(poll_interval, max(0, deadline_at - now)))
    logger.info("Downloading Qualtrics response export")
    response = _request(session, "GET", root + "/" + file_id + "/file", headers=headers, timeout=(10, 60)); _raise_for_status(response)
    try: archive = zipfile.ZipFile(io.BytesIO(response.content))
    except zipfile.BadZipFile as e: raise QualtricsError("Qualtrics download is not a ZIP") from e
    csv_names = [n for n in archive.namelist() if n.lower().endswith(".csv")]
    if len(csv_names) != 1: raise QualtricsError("Qualtrics ZIP must contain one CSV")
    rows = list(csv.reader(io.StringIO(archive.read(csv_names[0]).decode("utf-8-sig"))))
    if not rows or rows[0] != ["EndDate"]: raise QualtricsError("export CSV must contain only EndDate")
    data_start = 1
    if len(rows) > 1 and len(rows[1]) == 1 and rows[1][0].startswith("End Date"): data_start = 2
    if len(rows) > data_start:
        try: metadata = json.loads(rows[data_start][0])
        except (json.JSONDecodeError, TypeError): metadata = None
        if isinstance(metadata, dict) and metadata.get("ImportId") == "endDate": data_start += 1
    if any(len(row) != 1 or not row[0] for row in rows[data_start:]): raise QualtricsError("export contains an invalid EndDate row")
    result = [row[0] for row in rows[data_start:]]
    logger.info("Parsed %d registration timestamps from Qualtrics", len(result))
    return result

def get_quota_count(survey_id, quota_id, *, base_url, api_key, session=None):
    logger.info("Fetching Qualtrics quota count")
    session = session or requests.Session(); url = base_url.rstrip("/") + f"/survey-definitions/{survey_id}/quotas/{quota_id}"
    result = _json(_request(session, "GET", url, headers={"X-API-TOKEN": api_key, "Accept": "application/json"}, timeout=(10, 30))).get("result", {})
    value = result.get("Count")
    if isinstance(value, bool) or not isinstance(value, (int, float)) or int(value) != value or value < 0: raise QualtricsError("quota response lacks a valid Count")
    logger.info("Qualtrics quota count received: %d", int(value))
    return int(value)
