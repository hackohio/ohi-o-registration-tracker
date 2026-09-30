from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
import logging
from datetime import date, datetime
from zoneinfo import ZoneInfo
from . import charts, qualtrics
from .registrations import load_aggregate, load_participant_aggregate, timeline

logger = logging.getLogger(__name__)

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
    marion: int | None = None
    professionals: int | None = None


def _run_parallel(calls, *, session):
    if session is not None:
        return [call() for call in calls]
    with ThreadPoolExecutor(max_workers=len(calls)) as executor:
        futures = [executor.submit(call) for call in calls]
        return [future.result() for future in futures]


def build(settings, *, today=None, session=None):
    event = settings.event; today = today or datetime.now(ZoneInfo(event.timezone)).date()
    if today > event.event_date: raise ValueError(f"{event.key}: event has ended")
    professional_fields = (
        getattr(event, "professional_survey_id", None),
        getattr(event, "marion_quota_id", None),
    )
    if any(value is not None for value in professional_fields) and not all(
        value is not None for value in professional_fields
    ):
        raise ValueError(f"{event.key}: professional and Marion settings must be configured together")
    has_professional_counts = all(value is not None for value in professional_fields)
    point = (event.event_date - today).days
    logger.info("Building report for %s (%d days before event)", event.key, point)
    historical = load_aggregate(event.history.aggregate_output)
    participant_histories = {
        event.history.label: {day: values[0] for day, values in historical.items()}
    }
    participant_histories.update({
        label: load_participant_aggregate(path)
        for label, path in getattr(event.history, "participant_trends", ())
    })
    historical_values = historical.get(point, ("Reg was not open", "Reg was not open"))
    logger.info("Requesting Qualtrics registration exports")
    export_calls = [
        lambda: qualtrics.export_end_dates(event.participant_survey_id, base_url=settings.base_url, api_key=settings.api_key, timezone=event.timezone, session=session),
        lambda: qualtrics.export_end_dates(event.leader_survey_id, base_url=settings.base_url, api_key=settings.api_key, timezone=event.timezone, session=session),
    ]
    if has_professional_counts:
        export_calls.insert(
            1,
            lambda: qualtrics.export_end_dates(event.professional_survey_id, base_url=settings.base_url, api_key=settings.api_key, timezone=event.timezone, session=session),
        )
    export_results = _run_parallel(export_calls, session=session)
    if has_professional_counts:
        participants_dates, professionals_dates, leaders_dates = export_results
        participant_timestamps = [*participants_dates, *professionals_dates]
        professionals = timeline(professionals_dates, event.event_date, event.timezone, today=today)
        professional_count = professionals.get(point, 0)
    else:
        participants_dates, leaders_dates = export_results
        participant_timestamps = participants_dates
        professional_count = None
    participants = timeline(participant_timestamps, event.event_date, event.timezone, today=today)
    participant_count = participants.get(point, 0)
    leaders = timeline(leaders_dates, event.event_date, event.timezone, today=today)
    leader_count = leaders.get(point, 0)
    logger.info("Registration timelines built")
    marion_count = None
    if has_professional_counts:
        logger.info("Requesting Marion quota count")
        marion_count = qualtrics.get_quota_count(
            event.participant_survey_id,
            event.marion_quota_id,
            base_url=settings.base_url,
            api_key=settings.api_key,
            session=session,
        )
    logger.info(
        "Report counts from response exports: participants=%d, leaders=%d%s",
        participant_count,
        leader_count,
        f", professionals={professional_count}, Marion={marion_count}" if has_professional_counts else "",
    )
    logger.info("Rendering registration chart")
    chart = charts.make_chart(
        participants,
        leaders,
        historical,
        comparison_label=event.history.label,
        today_days_before=point,
        participant_histories=participant_histories,
    )
    logger.info("Report ready")
    return Report(
        event.name,
        event.event_date,
        point,
        datetime.now(ZoneInfo(event.timezone)),
        participant_count,
        leader_count,
        *historical_values,
        event.history.label,
        chart,
        marion=marion_count,
        professionals=professional_count,
    )
