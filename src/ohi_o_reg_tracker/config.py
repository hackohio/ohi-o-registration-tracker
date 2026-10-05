from dataclasses import dataclass
from datetime import date
from pathlib import Path
from urllib.parse import urlsplit
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
    participant_trends: tuple[tuple[str, Path], ...] = ()


@dataclass(frozen=True)
class Event:
    key: str
    name: str
    event_date: date | None
    timezone: str
    history: History
    participant_survey_id: str | None = None
    leader_survey_id: str | None = None
    professional_survey_id: str | None = None
    marion_quota_id: str | None = None
    participant_apps_script_url: str | None = None
    leader_apps_script_url: str | None = None


@dataclass(frozen=True)
class Settings:
    base_url: str | None
    event: Event
    api_key: str | None = None
    webhook_url: str | None = None
    sheets_api_secret: str | None = None


def _date(value, field):
    if not isinstance(value, date):
        raise ValueError(f"{field} must be a date")
    return value


def _valid_apps_script_url(value):
    if not isinstance(value, str): return False
    try:
        parsed = urlsplit(value)
        return (
            parsed.scheme == "https"
            and parsed.hostname == "script.google.com"
            and parsed.netloc.casefold() == "script.google.com"
            and parsed.username is None
            and parsed.password is None
            and re.fullmatch(r"/macros/s/[A-Za-z0-9_-]+/exec", parsed.path) is not None
            and not parsed.query
            and not parsed.fragment
        )
    except ValueError:
        return False


def load_events(path="events.toml"):
    with open(path, "rb") as f: raw = tomllib.load(f)
    qualtrics = raw.get("qualtrics", {})
    base_url = qualtrics.get("base_url") if isinstance(qualtrics, dict) else None
    result = {}
    for key, value in raw.get("events", {}).items():
        try:
            h = value["history"]
            participant_trends = tuple(
                (trend["label"], Path(trend["aggregate_output"]))
                for trend in h.get("participant_trends", [])
            )
            history = History(h["label"], _date(h["event_date"], "history.event_date"), Path(h["participants_input"]), Path(h["leaders_input"]), Path(h["aggregate_output"]), participant_trends)
            event = Event(
                key=key,
                name=value["name"],
                event_date=_date(value["event_date"], "event_date") if "event_date" in value else None,
                timezone=value["timezone"],
                history=history,
                participant_survey_id=value.get("participant_survey_id"),
                leader_survey_id=value.get("leader_survey_id"),
                professional_survey_id=value.get("professional_survey_id"),
                marion_quota_id=value.get("marion_quota_id"),
                participant_apps_script_url=value.get("participant_apps_script_url"),
                leader_apps_script_url=value.get("leader_apps_script_url"),
            )
            ZoneInfo(event.timezone)
        except (KeyError, TypeError, ZoneInfoNotFoundError) as e:
            raise ValueError(f"invalid event {key}: {e}") from e
        result[key] = event
    return base_url, result


def settings_for(key, *, path="events.toml", require_credentials=True, today=None, participant_only=False):
    _load_dotenv()
    base_url, events = load_events(path)
    if key not in events: raise ValueError(f"unknown event: {key}")
    event = events[key]; today = today or date.today()
    errors = []
    for name in ("name", "event_date", "timezone"):
        if not getattr(event, name): errors.append(f"{name} is required")

    professional_fields = (
        ("professional_survey_id", "SV"),
        ("marion_quota_id", "QO"),
    )
    configured_professional_fields = [
        getattr(event, name) is not None for name, _ in professional_fields
    ]
    if any(configured_professional_fields) and not all(configured_professional_fields):
        errors.append("professional_survey_id and marion_quota_id must be configured together")
    has_professional = all(configured_professional_fields)
    if has_professional:
        for name, prefix in professional_fields:
            value = getattr(event, name)
            if not isinstance(value, str) or not re.fullmatch(fr"{prefix}_[A-Za-z0-9]+", value):
                errors.append(f"{name} must be a valid {prefix}_ ID")

    streams = ["participant"]
    if not participant_only: streams.append("leader")
    uses_qualtrics = False
    uses_sheets = False
    for stream in streams:
        survey_id = getattr(event, f"{stream}_survey_id")
        script_url = getattr(event, f"{stream}_apps_script_url")
        if (survey_id is None) == (script_url is None):
            errors.append(f"{stream} stream must configure exactly one Qualtrics survey ID or Apps Script URL")
            continue
        if survey_id is not None:
            uses_qualtrics = True
            if not isinstance(survey_id, str) or not re.fullmatch(r"SV_[A-Za-z0-9]+", survey_id):
                errors.append(f"{stream}_survey_id must be a valid SV_ ID")
        else:
            uses_sheets = True
            if not _valid_apps_script_url(script_url):
                errors.append(f"{stream}_apps_script_url must be an HTTPS script.google.com /exec URL")

    if has_professional:
        uses_qualtrics = True
        if event.participant_survey_id is None:
            errors.append("professional/Marion settings require a Qualtrics participant survey")
    if uses_qualtrics and (not isinstance(base_url, str) or not base_url):
        errors.append("qualtrics.base_url is required for Qualtrics sources")
    if event.event_date is not None and event.event_date < today: errors.append("event_date is in the past")
    if not event.history.aggregate_output.is_file():
        errors.append(f"missing aggregate: {event.history.aggregate_output}")
    else:
        try:
            from .registrations import load_aggregate, load_participant_aggregate
            load_aggregate(event.history.aggregate_output)
            for _, path in event.history.participant_trends:
                if not path.is_file():
                    errors.append(f"missing participant trend: {path}")
                else:
                    load_participant_aggregate(path)
        except ValueError as e:
            errors.append(str(e))
    if require_credentials:
        if uses_qualtrics and not os.getenv("QUALTRICS_API_KEY"):
            errors.append("QUALTRICS_API_KEY is missing")
        sheets_api_secret = os.getenv("GOOGLE_SHEETS_API_SECRET")
        if uses_sheets and not sheets_api_secret:
            errors.append("GOOGLE_SHEETS_API_SECRET is missing")
        if not participant_only and not os.getenv("DISCORD_WEBHOOK_URL"):
            errors.append("DISCORD_WEBHOOK_URL is missing")
    else:
        sheets_api_secret = os.getenv("GOOGLE_SHEETS_API_SECRET")
    if errors: raise ValueError(f"{key}: " + "; ".join(errors))
    return Settings(base_url, event, os.getenv("QUALTRICS_API_KEY") or None, os.getenv("DISCORD_WEBHOOK_URL") or None, sheets_api_secret or None)


def validate_history(event):
    for p in (event.history.participants_input, event.history.leaders_input):
        if not p.is_file(): raise ValueError(f"missing history input: {p}")
    return event
