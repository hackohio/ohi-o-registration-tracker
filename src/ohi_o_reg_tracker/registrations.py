import csv
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

FORMAT = "%Y-%m-%d %H:%M:%S"

def read_end_dates(path):
    path = Path(path)
    with path.open(newline="", encoding="utf-8-sig") as f:
        rows = csv.DictReader(f)
        if rows.fieldnames != ["EndDate"]:
            raise ValueError(f"{path}: expected exactly an EndDate column")
        values = []
        for number, row in enumerate(rows, 2):
            value = row.get("EndDate", "")
            try: values.append(datetime.strptime(value, FORMAT))
            except (TypeError, ValueError) as e: raise ValueError(f"{path}, row {number}: invalid EndDate") from e
        return values

def timeline(timestamps, event_date, timezone, today=None):
    ZoneInfo(timezone)  # validate even when input is empty
    today = today or date.today()
    parsed = []
    for i, value in enumerate(timestamps, 1):
        if isinstance(value, datetime): dt = value
        else:
            try: dt = datetime.strptime(value, FORMAT)
            except (TypeError, ValueError) as e: raise ValueError(f"row {i}: invalid timestamp") from e
        day = dt.date()
        if day > event_date: raise ValueError(f"row {i}: timestamp is after event date")
        parsed.append(day)
    first = min(parsed, default=event_date)
    counts = {}
    for day in parsed: counts[day] = counts.get(day, 0) + 1
    result = {}; total = 0; day = first
    while day <= event_date:
        total += counts.get(day, 0)
        if day <= today: result[(event_date - day).days] = total
        day += timedelta(days=1)
    return dict(sorted(result.items(), reverse=True))

def _load_series(path, columns):
    path = Path(path)
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames != ["days_before", *columns]:
            raise ValueError(f"{path}: invalid header")
        try:
            rows = [(int(row["days_before"]), *(int(row[column]) for column in columns)) for row in reader]
        except (KeyError, TypeError, ValueError) as e:
            raise ValueError(f"{path}: invalid aggregate values") from e
    if not rows:
        raise ValueError(f"{path}: aggregate is empty")
    days = [row[0] for row in rows]
    if days[-1] != 0 or len(set(days)) != len(days) or days != list(range(days[0], -1, -1)):
        raise ValueError(f"{path}: days_before must be contiguous and end at 0")
    if any(any(value < 0 for value in row[1:]) for row in rows):
        raise ValueError(f"{path}: counts cannot be negative")
    if any(rows[i][j] > rows[i + 1][j] for i in range(len(rows) - 1) for j in range(1, len(columns) + 1)):
        raise ValueError(f"{path}: counts must not decrease toward event day")
    return rows


def load_aggregate(path):
    return {row[0]: (row[1], row[2]) for row in _load_series(path, ("participants", "leaders"))}


def load_participant_aggregate(path):
    return {row[0]: row[1] for row in _load_series(path, ("participants",))}

def write_aggregate(path, participants, leaders):
    days = sorted(set(participants) | set(leaders), reverse=True)
    if not days or days[-1] != 0: raise ValueError("timelines must include event day")
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True); tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", newline="", encoding="utf-8") as f:
        out = csv.writer(f); out.writerow(("days_before", "participants", "leaders"))
        for d in days: out.writerow((d, participants.get(d, 0), leaders.get(d, 0)))
    tmp.replace(path)
