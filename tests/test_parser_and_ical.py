from __future__ import annotations

from datetime import datetime
from pathlib import Path

from app.config import TIMEZONE
from app.services.ical_adapter import parse_hard_exclusions
from app.services.interval_parser import parse_partner_text


def test_interval_parser_treats_unprefixed_lines_as_available():
    text = "\n".join(
        [
            "2026-08-01 18:00 to 2026-08-03 18:00",
            "exclude: 2026-08-10 to 2026-08-12",
            "unavailable: 2026-08-20 to 2026-08-21",
        ]
    )

    parsed = parse_partner_text(text, clarification_responses={})

    assert len(parsed.intervals) == 3
    assert len(parsed.clarifications) == 0
    assert parsed.intervals[0].type == "kid_free"
    assert parsed.intervals[1].type == "exclusion"
    assert parsed.intervals[2].type == "exclusion"


def test_interval_parser_supports_date_only_hyphen_ranges_inclusive():
    text = "\n".join(
        [
            "2026-08-01 - 2026-08-03",
            "exclude: 2026-08-10 - 2026-08-12",
        ]
    )

    parsed = parse_partner_text(text, clarification_responses={})

    assert len(parsed.intervals) == 2
    assert len(parsed.clarifications) == 0

    include_interval = parsed.intervals[0]
    exclude_interval = parsed.intervals[1]

    assert include_interval.type == "kid_free"
    assert include_interval.start.isoformat() == "2026-08-01T00:00:00+01:00"
    assert include_interval.end.isoformat() == "2026-08-03T23:59:59.999999+01:00"

    assert exclude_interval.type == "exclusion"
    assert exclude_interval.start.isoformat() == "2026-08-10T00:00:00+01:00"
    assert exclude_interval.end.isoformat() == "2026-08-12T23:59:59.999999+01:00"


def test_ical_parser_extracts_hard_exclusions():
    ics = """BEGIN:VCALENDAR
BEGIN:VEVENT
DTSTART:20260805T090000Z
DTEND:20260805T120000Z
SUMMARY:Travel block
END:VEVENT
END:VCALENDAR
"""

    intervals = parse_hard_exclusions(ical_content=ics, ical_file_path=None)

    assert len(intervals) == 1
    assert intervals[0].type == "hard_exclusion"
    assert intervals[0].reason == "Travel block"


def test_ical_parser_filters_out_of_window_events():
    ics = """BEGIN:VCALENDAR
BEGIN:VEVENT
DTSTART:20260805T090000Z
DTEND:20260805T120000Z
SUMMARY:In window
END:VEVENT
BEGIN:VEVENT
DTSTART:20141201T090000Z
DTEND:20141201T100000Z
SUMMARY:Way in the past - out of window
END:VEVENT
BEGIN:VEVENT
DTSTART:20300101T090000Z
DTEND:20300101T100000Z
SUMMARY:Far future - out of window
END:VEVENT
END:VCALENDAR
"""

    w_start = datetime(2026, 7, 20, tzinfo=TIMEZONE)
    w_end = datetime(2026, 9, 2, tzinfo=TIMEZONE)

    intervals = parse_hard_exclusions(ical_content=ics, ical_file_path=None, window_start=w_start, window_end=w_end)

    assert len(intervals) == 1
    assert intervals[0].reason == "In window"
