from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from app.config import TIMEZONE
from app.models import TimeInterval

# Extra padding either side of the holiday window to include partially-overlapping events.
_WINDOW_BUFFER = timedelta(days=1)


@dataclass(frozen=True)
class CalendarClassifiedIntervals:
    hard_exclusions: list[TimeInterval]
    together_windows: list[TimeInterval]
    ignored_events: list[dict]


def _parse_dt(raw: str) -> datetime:
    """Parse datetime from iCalendar format, properly handling timezones."""
    raw = raw.strip()
    if raw.endswith("Z"):
        # Parse UTC time and convert to target timezone
        dt = datetime.strptime(raw, "%Y%m%dT%H%M%SZ")
        dt = dt.replace(tzinfo=ZoneInfo("UTC"))  # Mark as UTC
        return dt.astimezone(TIMEZONE)  # Convert to target timezone
    if "T" in raw:
        # Naive datetime (no timezone indicator), assume target timezone
        dt = datetime.strptime(raw, "%Y%m%dT%H%M%S")
    else:
        # All-day event (date only), start at midnight
        dt = datetime.strptime(raw, "%Y%m%d")
    return dt.replace(tzinfo=TIMEZONE)


def _read_ics(ical_content: str | None, ical_file_path: str | None) -> str:
    if ical_content:
        return ical_content
    if ical_file_path:
        return Path(ical_file_path).read_text(encoding="utf-8")
    return ""


def _iter_ical_events(text: str):
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
                yield dt_start, dt_end, summary
            continue

        if not in_event:
            continue

        if line.startswith("DTSTART"):
            dt_start = line.split(":", 1)[1]
        elif line.startswith("DTEND"):
            dt_end = line.split(":", 1)[1]
        elif line.startswith("SUMMARY"):
            summary = line.split(":", 1)[1]


def parse_google_calendar_intervals(
    ical_content: str,
    window_start: datetime,
    window_end: datetime,
    *,
    hard_tags: tuple[str, ...] = ("BLOCK", "UNAVAILABLE"),
    together_tags: tuple[str, ...] = ("TOGETHER",),
    default_mode: str = "ignore_untagged",
) -> CalendarClassifiedIntervals:
    """Classify Google calendar events into hard exclusions, together windows, or ignored events.

    Tag matching is case-insensitive and expects bracket-style tags in summary,
    such as [BLOCK], [UNAVAILABLE], or [TOGETHER].
    """
    text = _read_ics(ical_content, None)
    if not text:
        return CalendarClassifiedIntervals(hard_exclusions=[], together_windows=[], ignored_events=[])

    hard_tags_upper = tuple(t.strip().upper() for t in hard_tags if t and t.strip())
    together_tags_upper = tuple(t.strip().upper() for t in together_tags if t and t.strip())
    hard_exclusions: list[TimeInterval] = []
    together_windows: list[TimeInterval] = []
    ignored_events: list[dict] = []

    lo = window_start - _WINDOW_BUFFER
    hi = window_end + _WINDOW_BUFFER

    for idx, (dt_start, dt_end, summary) in enumerate(_iter_ical_events(text), start=1):
        ev_start = _parse_dt(dt_start)
        ev_end = _parse_dt(dt_end)
        if ev_end <= lo or ev_start >= hi:
            continue

        summary_upper = summary.upper()
        has_hard_tag = any(f"[{tag}]" in summary_upper for tag in hard_tags_upper)
        has_together_tag = any(f"[{tag}]" in summary_upper for tag in together_tags_upper)

        # Deterministic precedence when multiple tags appear.
        if has_hard_tag:
            classification = "hard"
        elif has_together_tag:
            classification = "together"
        elif default_mode == "hard_untagged":
            classification = "hard"
        else:
            classification = "ignored"

        if classification == "ignored":
            ignored_events.append(
                {
                    "event_id": f"gcal-{idx}",
                    "summary": summary or "Calendar event",
                    "start": ev_start.isoformat(),
                    "end": ev_end.isoformat(),
                    "reason": "Untagged event ignored by policy",
                }
            )
            continue

        interval = TimeInterval(
            id=f"gcal-{idx}",
            start=ev_start,
            end=ev_end,
            type="hard_exclusion" if classification == "hard" else "kid_free",
            confidence=1.0,
            source="google_calendar",
            reason=summary or "Google calendar event",
        )

        if classification == "hard":
            hard_exclusions.append(interval)
        else:
            together_windows.append(interval)

    return CalendarClassifiedIntervals(
        hard_exclusions=hard_exclusions,
        together_windows=together_windows,
        ignored_events=ignored_events,
    )


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
    for dt_start, dt_end, summary in _iter_ical_events(text):
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

    return intervals
