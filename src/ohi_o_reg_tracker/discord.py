import time
import requests

def send(report, webhook_url, *, session=None):
    session = session or requests.Session()
    payload = {"embeds": [{"title": report.event_name, "description": f"{report.days_before} days before the event", "fields": [{"name": "Participants", "value": f"{report.participants} (last year: {report.historical_participants})", "inline": True}, {"name": "Mentor/Judge", "value": f"{report.leaders} (last year: {report.historical_leaders})", "inline": True}], "image": {"url": "attachment://registration.png"}, "footer": {"text": f"Updated {report.updated_at.isoformat()}"}}]}
    response = session.post(webhook_url, data={"payload_json": __import__("json").dumps(payload)}, files={"file": ("registration.png", report.png, "image/png")}, timeout=(10, 30))
    if response.status_code == 429:
        try: delay = min(float(response.json().get("retry_after", 1)), 30)
        except (ValueError, TypeError): delay = 1
        time.sleep(delay)
        response = session.post(webhook_url, data={"payload_json": __import__("json").dumps(payload)}, files={"file": ("registration.png", report.png, "image/png")}, timeout=(10, 30))
    response.raise_for_status()
