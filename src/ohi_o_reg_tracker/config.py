from dataclasses import dataclass
from datetime import date
from pathlib import Path
import os, re, tomllib
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

def _load_dotenv(path=".env"):
    p = Path(path)
    if not p.is_file(): return
    for line in p.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip("'\""))

@dataclass(frozen=True)
class History:
    label: str
    event_date: date
    participants_input: Path
    leaders_input: Path
    aggregate_output: Path

@dataclass(frozen=True)
class Event:
    key: str
    name: str
    event_date: date
    timezone: str
    participant_survey_id: str
    participant_quota_id: str
    leader_survey_id: str
    leader_quota_id: str
    history: History

@dataclass(frozen=True)
class Settings:
    base_url: str
    event: Event
    api_key: str | None = None
    webhook_url: str | None = None

def _date(value, field):
    if not isinstance(value, date):
        raise ValueError(f"{field} must be a date")
    return value

def load_events(path="events.toml"):
    with open(path, "rb") as f: raw = tomllib.load(f)
    q = raw.get("qualtrics", {})
    if not isinstance(q.get("base_url"), str) or not q["base_url"]: raise ValueError("qualtrics.base_url is required")
    result = {}
    for key, value in raw.get("events", {}).items():
        try:
            h = value["history"]
            history = History(h["label"], _date(h["event_date"], "history.event_date"), Path(h["participants_input"]), Path(h["leaders_input"]), Path(h["aggregate_output"]))
            event = Event(key, value["name"], _date(value["event_date"], "event_date"), value["timezone"], value["participant_survey_id"], value["participant_quota_id"], value["leader_survey_id"], value["leader_quota_id"], history)
            ZoneInfo(event.timezone)
        except (KeyError, TypeError, ZoneInfoNotFoundError) as e:
            raise ValueError(f"invalid event {key}: {e}") from e
        result[key] = event
    return q["base_url"], result

def settings_for(key, *, path="events.toml", require_credentials=True, today=None, participant_only=False):
    _load_dotenv()
    base_url, events = load_events(path)
    if key not in events: raise ValueError(f"unknown event: {key}")
    event = events[key]; today = today or date.today()
    errors = []
    for name in ("name", "event_date", "timezone"):
        if not getattr(event, name): errors.append(f"{name} is required")
    ids = (("participant_survey_id", "SV"), ("participant_quota_id", "QO"))
    if not participant_only: ids += (("leader_survey_id", "SV"), ("leader_quota_id", "QO"))
    for name, prefix in ids:
        if not re.fullmatch(fr"{prefix}_[A-Za-z0-9]+", getattr(event, name)):
            errors.append(f"{name} must be a valid {prefix}_ ID")
    if event.event_date < today: errors.append("event_date is in the past")
    if not event.history.aggregate_output.is_file():
        errors.append(f"missing aggregate: {event.history.aggregate_output}")
    else:
        try:
            from .registrations import load_aggregate
            load_aggregate(event.history.aggregate_output)
        except ValueError as e:
            errors.append(str(e))
    if require_credentials:
        if not os.getenv("QUALTRICS_API_KEY"): errors.append("QUALTRICS_API_KEY is missing")
        if not participant_only and not os.getenv("DISCORD_WEBHOOK_URL"): errors.append("DISCORD_WEBHOOK_URL is missing")
    if errors: raise ValueError(f"{key}: " + "; ".join(errors))
    return Settings(base_url, event, os.getenv("QUALTRICS_API_KEY"), os.getenv("DISCORD_WEBHOOK_URL"))

def validate_history(event):
    for p in (event.history.participants_input, event.history.leaders_input):
        if not p.is_file(): raise ValueError(f"missing history input: {p}")
    return event
