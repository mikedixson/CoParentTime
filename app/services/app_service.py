from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Literal
from uuid import uuid4

from app import db
from app.config import RuntimeConfig, TIMEZONE, get_runtime_config
from app.models import ChristmasContext, ClarificationItem, FollowingWeekendContext, ParentSide, ParseResult, PlanResultPayload, PlanRunRequest
from app.services.candidate_generator import generate_candidates, generate_christmas_candidates
from app.services.clarification_engine import build_clarification_payload, is_critical_ambiguity
from app.services.constraint_engine import parent_covering_window, validate_candidates
from app.services.google_calendar import GoogleCalendarFetchError, fetch_google_calendar_ics, redact_google_calendar_url
from app.services.hashing import stable_input_hash
from app.services.ical_adapter import parse_google_calendar_intervals, parse_hard_exclusions
from app.services.interval_parser import parse_partner_text
from app.services.report_renderer import write_artifacts
from app.services.scoring_engine import score_and_rank


def _handover_datetime(handover_day: date, runtime_config: RuntimeConfig) -> datetime:
    return datetime.combine(handover_day, runtime_config.handover_time_for(handover_day), tzinfo=TIMEZONE)


def _window_datetimes(req: PlanRunRequest, runtime_config: RuntimeConfig) -> tuple[datetime, datetime]:
    start = _handover_datetime(req.holiday_start, runtime_config)
    end = _handover_datetime(req.holiday_end, runtime_config)
    if start == end:
        end = _handover_datetime(req.holiday_end + timedelta(days=1), runtime_config)
    return start, end


def _planning_period_label(req: PlanRunRequest) -> str:
    if req.planning_period.strip():
        return req.planning_period.strip()
    return f"{req.holiday_start.isoformat()} to {req.holiday_end.isoformat()}"


def _following_weekend_context(req: PlanRunRequest, runtime_config: RuntimeConfig) -> FollowingWeekendContext:
    days_until_friday = (4 - req.holiday_end.weekday()) % 7 or 7
    friday = req.holiday_end + timedelta(days=days_until_friday)
    labels: dict[ParentSide, str] = {"this_parent": runtime_config.dad_title, "other_parent": runtime_config.mum_title}
    return FollowingWeekendContext(
        start=friday,
        end=friday + timedelta(days=2),
        parent=req.following_weekend_parent,
        parent_label=labels[req.following_weekend_parent] if req.following_weekend_parent else None,
    )


def _christmas_context(
    req: PlanRunRequest, runtime_config: RuntimeConfig, start: datetime, end: datetime,
) -> tuple[ChristmasContext | None, str | None]:
    if not runtime_config.christmas_split_date and not req.christmas_day_parent:
        return None, None
    days = [
        date(year, 12, 25) for year in range(start.year, end.year + 1)
        if datetime(year, 12, 25, tzinfo=TIMEZONE) < end
        and datetime(year, 12, 26, tzinfo=TIMEZONE) > start
    ]
    if not days and not req.christmas_day_parent:
        return None, None
    labels: dict[ParentSide, str] = {"this_parent": runtime_config.dad_title, "other_parent": runtime_config.mum_title}
    context = ChristmasContext(
        christmas_day=days[0] if len(days) == 1 else None,
        requested_parent=req.christmas_day_parent,
        requested_parent_label=labels[req.christmas_day_parent] if req.christmas_day_parent else None,
        parent_labels=labels,
        mode="configured_split" if runtime_config.christmas_split_date else "manual_parent",
    )
    if len(days) != 1:
        return context, "Christmas planning requires exactly one Christmas Day in the planning window."
    day = days[0]
    day_start = datetime.combine(day, time.min, tzinfo=TIMEZONE)
    day_end = day_start + timedelta(days=1)
    if runtime_config.christmas_split_date:
        month, day_number = map(int, runtime_config.christmas_split_date.split("-"))
        split_day = date(day.year + (month == 1), month, day_number)
        context.split_at = _handover_datetime(split_day, runtime_config)
    if start > day_start or end < day_end:
        return context, "Christmas planning requires the whole of 25 December, from midnight to midnight, inside the planning window."
    if context.split_at:
        if not start < context.split_at < end:
            return context, "The configured Christmas split must be strictly inside the planning window."
        if day_start < context.split_at < day_end:
            return context, "The configured Christmas split cannot divide Christmas Day. Choose a handover outside 25 December or exactly at midnight."
    return context, None


def _clip_to_window(intervals: list, window_start: datetime, window_end: datetime) -> list:
    """Drop intervals entirely outside the window; clamp those that partially overlap."""
    clipped = []
    for iv in intervals:
        if iv.end <= window_start or iv.start >= window_end:
            continue  # entirely outside — discard
        if iv.start < window_start or iv.end > window_end:
            iv = iv.model_copy(update={
                "start": max(iv.start, window_start),
                "end": min(iv.end, window_end),
            })
        clipped.append(iv)
    return clipped


def _subtract_exclusions_from_kid_free(
    kid_free: list[TimeInterval], exclusions: list[TimeInterval]
) -> list[TimeInterval]:
    """Remove exclusion periods from partner availability windows, splitting as needed.

    Partner ``exclude:`` dates mean Preet is unavailable during those periods.
    They must not be counted as couple-time coverage even when Mum has the child.
    """
    result: list[TimeInterval] = []
    for kf in kid_free:
        segments: list[tuple[datetime, datetime]] = [(kf.start, kf.end)]
        for excl in exclusions:
            new_segs: list[tuple[datetime, datetime]] = []
            for seg_s, seg_e in segments:
                ov_s = max(seg_s, excl.start)
                ov_e = min(seg_e, excl.end)
                if ov_s >= ov_e:
                    new_segs.append((seg_s, seg_e))
                    continue
                if seg_s < ov_s:
                    new_segs.append((seg_s, ov_s))
                if ov_e < seg_e:
                    new_segs.append((ov_e, seg_e))
            segments = new_segs
        for i, (s, e) in enumerate(segments):
            result.append(kf.model_copy(update={
                "id": f"{kf.id}-s{i}" if len(segments) > 1 else kf.id,
                "start": s,
                "end": e,
            }))
    return result


def _pre_holiday_context(req: PlanRunRequest) -> tuple[datetime, bool]:
    pre_holiday_date = req.holiday_start - timedelta(days=1)
    is_weekday = pre_holiday_date.weekday() < 5
    pre_holiday_dt = datetime.combine(pre_holiday_date, time.min, tzinfo=TIMEZONE)
    return pre_holiday_dt, is_weekday


def run_planning(req: PlanRunRequest) -> PlanResultPayload:
    run_id = str(uuid4())
    runtime_config = get_runtime_config()
    start, end = _window_datetimes(req, runtime_config)
    planning_period = _planning_period_label(req)
    following_weekend = _following_weekend_context(req, runtime_config)
    christmas, christmas_error = _christmas_context(req, runtime_config, start, end)

    payload = req.model_dump(mode="json")
    payload["planning_period"] = planning_period
    input_hash = stable_input_hash(payload)

    persisted_payload = dict(payload)
    persisted_payload["google_calendar_ical_url"] = redact_google_calendar_url(
        persisted_payload.get("google_calendar_ical_url")
    )

    db.save_run_header(run_id, planning_period, "started", input_hash)
    db.save_run_input(run_id, persisted_payload)
    if christmas_error:
        result = PlanResultPayload(
            run_id=run_id,
            status="blocked",
            following_weekend=following_weekend,
            christmas=christmas,
            input_summary={
                "planning_period": planning_period,
                "holiday_start": str(req.holiday_start),
                "holiday_end": str(req.holiday_end),
                "timezone": "Europe/London",
            },
            parse_audit=[],
            constraint_audit=[{"status": "blocked", "reason": christmas_error}],
            metadata={"input_hash": input_hash, "reason": christmas_error},
        )
        result.artifacts = write_artifacts(result)
        db.save_audit(run_id, "constraint", result.constraint_audit)
        db.save_result(run_id, result.model_dump(mode="json"))
        db.save_run_header(run_id, planning_period, "blocked", input_hash)
        return result
    if runtime_config.partner_enabled:
        parse_result = parse_partner_text(req.partner_text, req.clarification_responses)
    else:
        parse_result = ParseResult(intervals=[], clarifications=[])
    pre_holiday_dt, is_weekday = _pre_holiday_context(req)
    if is_weekday and not req.pre_holiday_schoolday_confirmed:
        weekday_name = pre_holiday_dt.strftime("%A")
        date_iso = pre_holiday_dt.date().isoformat()
        pickup_time = runtime_config.pre_holiday_school_pickup_time
        parse_result.clarifications.append(
            ClarificationItem(
                id="pre-holiday-schoolday",
                prompt=(
                    "The day before holiday start appears to be a school day "
                    f"({date_iso}, {weekday_name}). Please confirm school pick-up handover at {pickup_time}."
                ),
                raw_text=(
                    "Missing confirmation for pre-holiday school-day handover "
                    f"on {date_iso} ({weekday_name}) at {pickup_time}."
                ),
            )
        )

    normalized_clarifications = [
        c if isinstance(c, dict) else c.model_dump() for c in parse_result.clarifications
    ]
    if is_critical_ambiguity(parse_result.clarifications):
        result = PlanResultPayload(
            run_id=run_id,
            status="needs_clarification",
            following_weekend=following_weekend,
            christmas=christmas,
            input_summary={
                "planning_period": planning_period,
                "holiday_start": str(req.holiday_start),
                "holiday_end": str(req.holiday_end),
                "timezone": "Europe/London",
                "boundary_policy": req.options.get("boundary_policy", "Strict"),
                "terminal_exception": bool(req.options.get("terminal_exception", False)),
            },
            parse_audit=[i.model_dump(mode="json") for i in parse_result.intervals],
            clarifications=parse_result.clarifications,
            metadata={"input_hash": input_hash},
        )
        db.save_clarifications(run_id, normalized_clarifications, req.clarification_responses, "open")
        db.save_result(run_id, result.model_dump(mode="json"))
        db.save_run_header(run_id, planning_period, "needs_clarification", input_hash)
        return result

    hard_exclusions = parse_hard_exclusions(req.ical_content, req.ical_file_path, window_start=start, window_end=end)
    calendar_together_windows = []
    ignored_google_events: list[dict] = []
    google_calendar_warnings: list[str] = []

    if req.google_calendar_ical_url and req.google_calendar_ical_url.strip():
        try:
            remote_ics = fetch_google_calendar_ics(req.google_calendar_ical_url.strip())
        except GoogleCalendarFetchError as exc:
            google_calendar_warnings.append(str(exc))
            remote_ics = ""

        if remote_ics:
            classified = parse_google_calendar_intervals(
                remote_ics,
                start,
                end,
                hard_tags=runtime_config.calendar_event_policy_hard_tags,
                together_tags=runtime_config.calendar_event_policy_together_tags,
                default_mode=runtime_config.calendar_event_policy_default_mode,
            )
            hard_exclusions.extend(classified.hard_exclusions)
            calendar_together_windows.extend(classified.together_windows)
            ignored_google_events.extend(classified.ignored_events)

    hard_exclusions = _clip_to_window(hard_exclusions, start, end)
    calendar_together_windows = _clip_to_window(calendar_together_windows, start, end)

    partner_intervals = _clip_to_window(parse_result.intervals, start, end)
    user_exclusions = [i for i in partner_intervals if i.type in {"exclusion"}]
    kid_free_raw = [i for i in partner_intervals if i.type == "kid_free"]
    kid_free_raw.extend(calendar_together_windows)
    # Subtract partner exclusion periods from availability windows so that
    # couple-time coverage is not credited for dates Preet is unavailable.
    kid_free = _subtract_exclusions_from_kid_free(kid_free_raw, user_exclusions)

    if christmas and christmas.split_at:
        candidates = generate_christmas_candidates(start, end, christmas.split_at)
    else:
        candidates = generate_candidates(
            start,
            end,
            handover_at=lambda handover_day: _handover_datetime(handover_day, runtime_config),
        )
    christmas_window = None
    christmas_owner: Literal["Dad", "Mum"] | None = None
    if christmas and christmas.christmas_day:
        day_start = datetime.combine(christmas.christmas_day, time.min, tzinfo=TIMEZONE)
        christmas_window = (day_start, day_start + timedelta(days=1))
        if req.christmas_day_parent:
            christmas_owner = "Dad" if req.christmas_day_parent == "this_parent" else "Mum"
        for candidate in candidates:
            owner = parent_covering_window(candidate, *christmas_window)
            candidate.christmas_day_parent = "this_parent" if owner == "Dad" else "other_parent" if owner == "Mum" else None
    # Only pass hard calendar exclusions to constraint validation.
    # Partner unavailability exclusions (user_exclusions) should not block Dad from being assigned;
    # they define when Dad must parent alone while partner is unavailable.
    valid_candidates, constraint_audit = validate_candidates(
        candidates,
        hard_exclusions,
        kid_free,
        partner_name=runtime_config.partner_name,
        christmas_window=christmas_window,
        christmas_owner=christmas_owner,
    )

    if not valid_candidates:
        result = PlanResultPayload(
            run_id=run_id,
            status="blocked",
            following_weekend=following_weekend,
            christmas=christmas,
            input_summary={
                "planning_period": planning_period,
                "holiday_start": str(req.holiday_start),
                "holiday_end": str(req.holiday_end),
                "timezone": "Europe/London",
            },
            parse_audit=[i.model_dump(mode="json") for i in (partner_intervals + calendar_together_windows + hard_exclusions)],
            constraint_audit=constraint_audit,
            metadata={
                "input_hash": input_hash,
                "reason": (
                    "No feasible Christmas schedule satisfies the configured split, Christmas Day selection, and hard calendar exclusions. "
                    "Review these settings or exclusions."
                    if christmas else "No valid candidates"
                ),
            },
        )
        result.metadata["calendar_event_audit"] = {
            "google_hard_exclusions": len([i for i in hard_exclusions if i.source == "google_calendar"]),
            "google_together_windows": len(calendar_together_windows),
            "google_ignored_events": len(ignored_google_events),
            "policy": {
                "default_mode": runtime_config.calendar_event_policy_default_mode,
                "hard_tags": list(runtime_config.calendar_event_policy_hard_tags),
                "together_tags": list(runtime_config.calendar_event_policy_together_tags),
            },
        }
        if ignored_google_events:
            result.metadata["google_ignored_events"] = ignored_google_events
        if google_calendar_warnings:
            result.metadata["google_calendar_warnings"] = google_calendar_warnings
        if christmas:
            result.artifacts = write_artifacts(result)
        db.save_result(run_id, result.model_dump(mode="json"))
        db.save_audit(run_id, "constraint", constraint_audit)
        db.save_run_header(run_id, planning_period, "blocked", input_hash)
        return result

    ranked = score_and_rank(valid_candidates)
    working_candidates = [c for c in ranked if c.overlap_hours > 0]
    non_working_candidates = [c for c in ranked if c.overlap_hours <= 0]

    # Prefer schedules where couple-time exists, but still keep non-working options visible.
    display_ranked = working_candidates + non_working_candidates
    primary = display_ranked[0]
    alternatives = display_ranked[1:3]

    relationship_audit = {
        "weights": {
            "fairness_gap_days": 100,
            "couple_time_overlap_hours": 10,
            "transitions": 2,
            "fragmentation": 1,
        },
        "selected_score": primary.score,
        "selected_plan_id": primary.plan_id,
        "selected_couple_time_working": primary.overlap_hours > 0,
        "couple_time_working_count": len(working_candidates),
        "couple_time_not_working_count": len(non_working_candidates),
    }

    result = PlanResultPayload(
        run_id=run_id,
        status="ok",
        following_weekend=following_weekend,
        christmas=christmas,
        input_summary={
            "planning_period": planning_period,
            "holiday_start": str(req.holiday_start),
            "holiday_end": str(req.holiday_end),
            "timezone": "Europe/London",
            "boundary_policy": req.options.get("boundary_policy", "Strict"),
            "terminal_exception": bool(req.options.get("terminal_exception", False)),
            "candidate_count": len(candidates),
            "feasible_count": len(ranked),
            "couple_time_working_count": len(working_candidates),
            "couple_time_not_working_count": len(non_working_candidates),
        },
        parse_audit=[i.model_dump(mode="json") for i in (partner_intervals + calendar_together_windows + hard_exclusions)],
        primary=primary,
        alternatives=alternatives,
        couple_time_views={
            "works": working_candidates[:3],
            "doesnt_work": non_working_candidates[:3],
        },
        relationship_optimization_audit=relationship_audit,
        constraint_audit=constraint_audit,
        metadata={"input_hash": input_hash},
    )
    result.metadata["calendar_event_audit"] = {
        "google_hard_exclusions": len([i for i in hard_exclusions if i.source == "google_calendar"]),
        "google_together_windows": len(calendar_together_windows),
        "google_ignored_events": len(ignored_google_events),
        "policy": {
            "default_mode": runtime_config.calendar_event_policy_default_mode,
            "hard_tags": list(runtime_config.calendar_event_policy_hard_tags),
            "together_tags": list(runtime_config.calendar_event_policy_together_tags),
        },
    }
    if ignored_google_events:
        result.metadata["google_ignored_events"] = ignored_google_events
    if google_calendar_warnings:
        result.metadata["google_calendar_warnings"] = google_calendar_warnings

    artifacts = write_artifacts(result)
    result.artifacts = artifacts

    db.save_candidates(run_id, [c.model_dump(mode="json") for c in ranked])
    db.save_audit(run_id, "constraint", constraint_audit)
    db.save_audit(run_id, "relationship_optimization", relationship_audit)
    db.save_result(run_id, result.model_dump(mode="json"))
    db.save_run_header(run_id, planning_period, "ok", input_hash)

    return result
