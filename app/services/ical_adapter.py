from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

from app.config import TIMEZONE
from app.models import TimeInterval

# Extra padding either side of the holiday window to include partially-overlapping events.
_WINDOW_BUFFER = timedelta(days=1)


def _parse_dt(raw: str) -> datetime:
    raw = raw.strip()
    if raw.endswith("Z"):
        dt = datetime.strptime(raw, "%Y%m%dT%H%M%SZ")
        return dt.replace(tzinfo=TIMEZONE)
    if "T" in raw:
        dt = datetime.strptime(raw, "%Y%m%dT%H%M%S")
    else:
        dt = datetime.strptime(raw, "%Y%m%d")
    return dt.replace(tzinfo=TIMEZONE)


def _read_ics(ical_content: str | None, ical_file_path: str | None) -> str:
    if ical_content:
        return ical_content
    if ical_file_path:
        return Path(ical_file_path).read_text(encoding="utf-8")
    return ""


def parse_hard_exclusions(
    ical_content: str | None,
    ical_file_path: str | None,
    window_start: datetime | None = None,
    window_end: datetime | None = None,
) -> list[TimeInterval]:
    text = _read_ics(ical_content, ical_file_path)
    if not text:
        return []

    intervals: list[TimeInterval] = []
    lines = [line.strip() for line in text.splitlines()]
    in_event = False
    dt_start = None
    dt_end = None
    summary = ""

    for line in lines:
        if line == "BEGIN:VEVENT":
            in_event = True
            dt_start = None
            dt_end = None
            summary = ""
            continue
        if line == "END:VEVENT" and in_event:
            in_event = False
            if dt_start and dt_end:
                ev_start = _parse_dt(dt_start)
                ev_end = _parse_dt(dt_end)
                if window_start and window_end:
                    lo = window_start - _WINDOW_BUFFER
                    hi = window_end + _WINDOW_BUFFER
                    if ev_end <= lo or ev_start >= hi:
                        continue
                idx = len(intervals) + 1
                intervals.append(
                    TimeInterval(
                        id=f"ical-{idx}",
                        start=ev_start,
                        end=ev_end,
                        type="hard_exclusion",
                        confidence=1.0,
                        source="ical",
                        reason=summary or "Calendar hard exclusion",
                    )
                )
            continue

        if not in_event:
            continue

        if line.startswith("DTSTART"):
            dt_start = line.split(":", 1)[1]
        elif line.startswith("DTEND"):
            dt_end = line.split(":", 1)[1]
        elif line.startswith("SUMMARY"):
            summary = line.split(":", 1)[1]

    return intervals
