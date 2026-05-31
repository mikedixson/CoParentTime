from __future__ import annotations

import re
from datetime import datetime, time

from app.config import TIMEZONE
from app.models import ClarificationItem, ParseResult, TimeInterval

RANGE_RE = re.compile(
    r"(?P<start>\d{4}-\d{1,2}-\d{1,2})(?:\s+(?P<start_time>\d{2}:\d{2}))?\s*(?:to|-|until)\s*"
    r"(?P<end>\d{4}-\d{1,2}-\d{1,2})(?:\s+(?P<end_time>\d{2}:\d{2}))?",
    flags=re.IGNORECASE,
)


def _normalize_date(day_str: str) -> str:
    """Zero-pad month and day so strptime always receives YYYY-MM-DD."""
    parts = day_str.split("-")
    return f"{parts[0]}-{int(parts[1]):02d}-{int(parts[2]):02d}"


def _parse_dt(day_str: str, time_str: str | None, default_end: bool) -> datetime:
    day = datetime.strptime(_normalize_date(day_str), "%Y-%m-%d").date()
    if time_str:
        t = datetime.strptime(time_str, "%H:%M").time()
    else:
        t = time.max if default_end else time.min
    return datetime.combine(day, t, tzinfo=TIMEZONE)


def parse_partner_text(partner_text: str, clarification_responses: dict[str, str]) -> ParseResult:
    intervals: list[TimeInterval] = []
    clarifications: list[ClarificationItem] = []

    lines = [line.strip() for line in partner_text.splitlines() if line.strip()]
    for idx, line in enumerate(lines, start=1):
        lower = line.lower()
        line_type = "kid_free"
        payload = line

        if lower.startswith("exclude:") or lower.startswith("exclusion:") or lower.startswith("unavailable:"):
            line_type = "exclusion"
            payload = line.split(":", 1)[1].strip()
        elif lower.startswith("kidfree:") or lower.startswith("kid-free:") or lower.startswith("available:"):
            line_type = "kid_free"
            payload = line.split(":", 1)[1].strip()
        else:
            response = clarification_responses.get(f"line-{idx}", "").strip().lower()
            if response in {"exclusion", "exclude", "unavailable"}:
                line_type = "exclusion"

        match = RANGE_RE.search(payload)
        if not match:
            clarifications.append(
                ClarificationItem(
                    id=f"line-{idx}-range",
                    prompt="Could not parse date range. Use YYYY-MM-DD [HH:MM] to YYYY-MM-DD [HH:MM]",
                    raw_text=line,
                )
            )
            continue

        start = _parse_dt(match.group("start"), match.group("start_time"), default_end=False)
        end = _parse_dt(match.group("end"), match.group("end_time"), default_end=True)
        if end <= start:
            clarifications.append(
                ClarificationItem(
                    id=f"line-{idx}-order",
                    prompt="End must be after start",
                    raw_text=line,
                )
            )
            continue

        intervals.append(
            TimeInterval(
                id=f"text-{idx}",
                start=start,
                end=end,
                type=line_type,
                confidence=0.95,
                source="partner_text",
                reason="Parsed from partner text",
            )
        )

    return ParseResult(intervals=intervals, clarifications=clarifications)
