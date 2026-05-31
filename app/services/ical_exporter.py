from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from app.models import CandidatePlan, PlanResultPayload


def _format_dt(dt: datetime) -> str:
    """Format a datetime as a UTC iCal timestamp (YYYYMMDDTHHMMSSz)."""
    if dt.tzinfo is not None:
        dt_utc = dt.astimezone(timezone.utc)
    else:
        dt_utc = dt.replace(tzinfo=timezone.utc)
    return dt_utc.strftime("%Y%m%dT%H%M%SZ")


def _now_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _fold_line(line: str) -> str:
    """Fold long iCal lines at 75 octets as per RFC 5545."""
    if len(line.encode("utf-8")) <= 75:
        return line
    result = []
    encoded = line.encode("utf-8")
    pos = 0
    first = True
    while pos < len(encoded):
        chunk_size = 75 if first else 74  # 74 because of the leading space
        chunk = encoded[pos:pos + chunk_size]
        # Ensure we don't split a multi-byte character
        while len(chunk) > 0:
            try:
                chunk.decode("utf-8")
                break
            except UnicodeDecodeError:
                chunk = encoded[pos:pos + len(chunk) - 1]
        if first:
            result.append(chunk.decode("utf-8"))
            first = False
        else:
            result.append(" " + chunk.decode("utf-8"))
        pos += len(chunk)
    return "\r\n".join(result)


def _resolve_plan(result: PlanResultPayload, plan_id: str | None) -> CandidatePlan | None:
    """Return the plan matching plan_id, or the primary plan if plan_id is None."""
    if plan_id is None:
        return result.primary

    if result.primary and result.primary.plan_id == plan_id:
        return result.primary

    for alt in result.alternatives:
        if alt.plan_id == plan_id:
            return alt

    for view_plans in result.couple_time_views.values():
        for candidate in view_plans:
            if candidate.plan_id == plan_id:
                return candidate

    return result.primary


def generate_plan_ics(result: PlanResultPayload, plan_id: str | None = None) -> str:
    """Generate iCal (.ics) content for the schedule blocks of a plan.

    Args:
        result: The full plan result payload.
        plan_id: The plan to export.  If None, the primary plan is used.

    Returns:
        A string in iCalendar format (RFC 5545) suitable for saving as a .ics file.
    """
    plan = _resolve_plan(result, plan_id)
    planning_period = result.input_summary.get("planning_period", "Schedule")
    now = _now_stamp()

    lines: list[str] = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//CoParenTime//Schedule//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        _fold_line(f"X-WR-CALNAME:CoParenTime: {planning_period}"),
    ]

    if plan is not None:
        for block in plan.blocks:
            uid = str(uuid4()) + "@coparentime"
            dtstart = _format_dt(block.start)
            dtend = _format_dt(block.end)
            summary = f"{block.owner} parenting block"
            description = (
                f"CoParenTime schedule block\\n"
                f"Plan: {plan.plan_id}\\n"
                f"Fairness gap: {plan.fairness_gap_days} days"
            )
            lines += [
                "BEGIN:VEVENT",
                _fold_line(f"UID:{uid}"),
                f"DTSTAMP:{now}",
                f"DTSTART:{dtstart}",
                f"DTEND:{dtend}",
                _fold_line(f"SUMMARY:{summary}"),
                _fold_line(f"DESCRIPTION:{description}"),
                "END:VEVENT",
            ]

    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"
