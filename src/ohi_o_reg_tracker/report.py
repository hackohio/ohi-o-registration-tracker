from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import date, datetime
from zoneinfo import ZoneInfo
from . import charts, qualtrics
from .registrations import load_aggregate, timeline

@dataclass(frozen=True)
class Report:
    event_name: str
    event_date: date
    days_before: int
    updated_at: datetime
    participants: int
    leaders: int
    historical_participants: int | str
    historical_leaders: int | str
    comparison_label: str
    png: bytes


def _run_parallel(calls, *, session):
    if session is not None:
        return [call() for call in calls]
    with ThreadPoolExecutor(max_workers=len(calls)) as executor:
        futures = [executor.submit(call) for call in calls]
        return [future.result() for future in futures]


def build(settings, *, today=None, session=None):
    event = settings.event; today = today or datetime.now(ZoneInfo(event.timezone)).date()
    if today > event.event_date: raise ValueError(f"{event.key}: event has ended")
    point = (event.event_date - today).days
    historical = load_aggregate(event.history.aggregate_output)
    historical_values = historical.get(point, ("Reg was not open", "Reg was not open"))
    participants_dates, leaders_dates = _run_parallel([
        lambda: qualtrics.export_end_dates(event.participant_survey_id, base_url=settings.base_url, api_key=settings.api_key, timezone=event.timezone, session=session),
        lambda: qualtrics.export_end_dates(event.leader_survey_id, base_url=settings.base_url, api_key=settings.api_key, timezone=event.timezone, session=session),
    ], session=session)
    participants = timeline(participants_dates, event.event_date, event.timezone, today=today)
    leaders = timeline(leaders_dates, event.event_date, event.timezone, today=today)
    participant_count, leader_count = _run_parallel([
        lambda: qualtrics.get_quota_count(event.participant_survey_id, event.participant_quota_id, base_url=settings.base_url, api_key=settings.api_key, session=session),
        lambda: qualtrics.get_quota_count(event.leader_survey_id, event.leader_quota_id, base_url=settings.base_url, api_key=settings.api_key, session=session),
    ], session=session)
    return Report(event.name, event.event_date, point, datetime.now(ZoneInfo(event.timezone)), participant_count, leader_count, *historical_values, event.history.label, charts.make_chart(participants, leaders, historical, comparison_label=event.history.label, today_days_before=point))
