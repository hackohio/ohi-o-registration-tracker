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

def load_aggregate(path):
    path = Path(path)
    with path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if not rows or list(rows[0].keys()) != ["days_before", "participants", "leaders"]: raise ValueError(f"{path}: invalid header")
    try: data = [(int(r["days_before"]), int(r["participants"]), int(r["leaders"])) for r in rows]
    except (KeyError, ValueError) as e: raise ValueError(f"{path}: invalid aggregate values") from e
    days = [r[0] for r in data]
    if days[-1] != 0 or len(set(days)) != len(days) or days != list(range(days[0], -1, -1)): raise ValueError(f"{path}: days_before must be contiguous and end at 0")
    if any(p < 0 or l < 0 for _, p, l in data): raise ValueError(f"{path}: counts cannot be negative")
    if any(data[i][1] > data[i+1][1] or data[i][2] > data[i+1][2] for i in range(len(data)-1)): raise ValueError(f"{path}: counts must not decrease toward event day")
    return {d: (p, l) for d, p, l in data}

def write_aggregate(path, participants, leaders):
    days = sorted(set(participants) | set(leaders), reverse=True)
    if not days or days[-1] != 0: raise ValueError("timelines must include event day")
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True); tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", newline="", encoding="utf-8") as f:
        out = csv.writer(f); out.writerow(("days_before", "participants", "leaders"))
        for d in days: out.writerow((d, participants.get(d, 0), leaders.get(d, 0)))
    tmp.replace(path)
