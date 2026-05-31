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


def _validate_file_path(file_path: str, base_dir: Path | None = None) -> Path:
    """Validate file path to prevent directory traversal attacks.
    
    Args:
        file_path: The file path to validate
        base_dir: Optional base directory to restrict files to. If None, uses current directory.
        
    Raises:
        ValueError: If path is invalid or escapes base directory
    """
    if base_dir is None:
        base_dir = Path.cwd()
    
    try:
        # $codeql [py/path-injection] - Path is validated and resolved to ensure it's within base_dir
        resolved_path = Path(file_path).resolve()
        base_dir_resolved = base_dir.resolve()
        
        # Check if resolved path is within base directory
        try:
            resolved_path.relative_to(base_dir_resolved)
        except ValueError:
            raise ValueError(f"Path traversal detected: {file_path}")
        
        # Check if file exists
        # $codeql [py/path-injection] - Path has been validated to be within base_dir
        if not resolved_path.exists():
            raise ValueError(f"File not found: {file_path}")
        
        # Check if it's a file (not directory)
        # $codeql [py/path-injection] - Path has been validated to be within base_dir
        if not resolved_path.is_file():
            raise ValueError(f"Path is not a file: {file_path}")
        
        return resolved_path
    except (RuntimeError, OSError) as e:
        raise ValueError(f"Invalid file path: {file_path}") from e


def _read_ics(ical_content: str | None, ical_file_path: str | None) -> str:
    if ical_content:
        return ical_content
    if ical_file_path:
        try:
            validated_path = _validate_file_path(ical_file_path)
            # $codeql [py/path-injection] - Path has been validated by _validate_file_path()
            return validated_path.read_text(encoding="utf-8")
        except ValueError as e:
            raise ValueError(f"Cannot read iCal file: {e}") from e
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
