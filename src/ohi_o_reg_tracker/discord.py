import json
import logging
import time

import requests

logger = logging.getLogger(__name__)


def send(report, webhook_url, *, session=None):
    logger.info("Sending report to Discord")
    session = session or requests.Session()
    content = "\n".join(
        [
            f"**__{report.days_before}__ Days Before {report.event_name}**",
            f"- **Participants**: {report.participants} (_last year: {report.historical_participants}_)",
            f"- **Mentor/Judge**: {report.leaders} (_last year: {report.historical_leaders}_)",
            "────────────────",
        ]
    )
    payload = {"content": content}
    files = {"file": ("registration.png", report.png, "image/png")}
    response = session.post(
        webhook_url,
        data={"payload_json": json.dumps(payload)},
        files=files,
        timeout=(10, 30),
    )
    if response.status_code == 429:
        try:
            delay = min(float(response.json().get("retry_after", 1)), 30)
        except (ValueError, TypeError):
            delay = 1
        time.sleep(delay)
        response = session.post(
            webhook_url,
            data={"payload_json": json.dumps(payload)},
            files=files,
            timeout=(10, 30),
        )
    response.raise_for_status()
    logger.info("Discord report sent")
