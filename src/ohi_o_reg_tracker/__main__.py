import argparse, csv, logging, sys
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from .config import load_events, settings_for, validate_history
from .registrations import load_aggregate, load_participant_aggregate, read_end_dates, timeline, write_aggregate
from .report import build, fetch_timestamps
from . import charts, discord, qualtrics

def _run_parallel(calls):
    with ThreadPoolExecutor(max_workers=len(calls)) as executor:
        futures = [executor.submit(call) for call in calls]
        return [future.result() for future in futures]

def main(argv=None):
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser(prog="ohi_o_reg_tracker"); sub = parser.add_subparsers(dest="command", required=True)
    for name in ("check", "build-history", "preview-participants", "report"):
        p = sub.add_parser(name); p.add_argument("--event", required=True)
        if name == "report": p.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    try:
        _, events = load_events(); event = events.get(args.event)
        if event is None: raise ValueError(f"unknown event: {args.event}")
        if args.command == "build-history":
            validate_history(event); h = event.history
            p = timeline(read_end_dates(h.participants_input), h.event_date, event.timezone, today=h.event_date)
            l = timeline(read_end_dates(h.leaders_input), h.event_date, event.timezone, today=h.event_date)
            write_aggregate(h.aggregate_output, p, l)
            print(f"{h.aggregate_output} ({len(p)} rows)"); return 0
        settings = settings_for(args.event, participant_only=args.command == "preview-participants")
        if args.command == "check": print(f"{args.event}: ready"); return 0
        if args.command == "preview-participants":
            today = datetime.now(ZoneInfo(event.timezone)).date()
            has_professional_counts = event.professional_survey_id is not None
            export_calls = [
                lambda: fetch_timestamps(settings, "participant"),
            ]
            if has_professional_counts:
                export_calls.append(
                    lambda: qualtrics.export_end_dates(event.professional_survey_id, base_url=settings.base_url, api_key=settings.api_key, timezone=event.timezone)
                )
            export_results = _run_parallel(export_calls)
            dates = export_results[0]
            if has_professional_counts:
                professionals_dates = export_results[1]
                participant_timestamps = [*dates, *professionals_dates]
            else:
                professionals_dates = []
                participant_timestamps = dates
            current = timeline(participant_timestamps, event.event_date, event.timezone, today=today)
            if has_professional_counts:
                professional_current = timeline(
                    professionals_dates, event.event_date, event.timezone, today=today
                ).get((event.event_date - today).days, 0)
                marion_count = qualtrics.get_quota_count(
                    event.participant_survey_id,
                    event.marion_quota_id,
                    base_url=settings.base_url,
                    api_key=settings.api_key,
                )
            else:
                professional_current = None
                marion_count = None
            participant_count = current.get((event.event_date - today).days, 0)
            output = Path("artifacts") / f"{args.event}-participants.png"; output.parent.mkdir(exist_ok=True)
            historical = load_aggregate(event.history.aggregate_output)
            participant_histories = {
                event.history.label: {day: values[0] for day, values in historical.items()}
            }
            participant_histories.update({
                label: load_participant_aggregate(path)
                for label, path in getattr(event.history, "participant_trends", ())
            })
            output.write_bytes(charts.make_chart(
                current,
                None,
                historical,
                comparison_label=event.history.label,
                today_days_before=(event.event_date - today).days,
                participant_histories=participant_histories,
            ))
            breakdown = f"; Marion: {marion_count}; Professional: {professional_current}" if has_professional_counts else ""
            print(f"Participants: {participant_count}{breakdown}; source timestamps: {len(participant_timestamps)}; chart: {output}"); return 0
        result = build(settings)
        if args.dry_run:
            output = Path("artifacts") / f"{args.event}.png"; output.parent.mkdir(exist_ok=True); output.write_bytes(result.png)
            breakdown = f"; Marion: {result.marion}; Professional: {result.professionals}" if result.marion is not None and result.professionals is not None else ""
            print(f"{result.days_before} days before {result.event_name}; Participants: {result.participants} (last year: {result.historical_participants}){breakdown}; Mentor/Judge: {result.leaders} (last year: {result.historical_leaders}); chart: {output}")
        else: discord.send(result, settings.webhook_url)
        return 0
    except Exception as error:
        print(f"{getattr(args, 'event', '?')}: {getattr(args, 'command', 'command')} failed: {error}", file=sys.stderr); return 1

if __name__ == "__main__": sys.exit(main())
