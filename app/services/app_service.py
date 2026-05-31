from __future__ import annotations

from datetime import date, datetime, time, timedelta
from uuid import uuid4

from app import db
from app.config import RuntimeConfig, TIMEZONE, get_runtime_config
from app.models import ClarificationItem, ParseResult, PlanResultPayload, PlanRunRequest
from app.services.candidate_generator import generate_candidates
from app.services.clarification_engine import build_clarification_payload, is_critical_ambiguity
from app.services.constraint_engine import validate_candidates
from app.services.google_calendar import GoogleCalendarFetchError, fetch_google_calendar_ics, redact_google_calendar_url
from app.services.hashing import stable_input_hash
from app.services.ical_adapter import parse_hard_exclusions
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

    payload = req.model_dump(mode="json")
    payload["planning_period"] = planning_period
    input_hash = stable_input_hash(payload)

    persisted_payload = dict(payload)
    persisted_payload["google_calendar_ical_url"] = redact_google_calendar_url(
        persisted_payload.get("google_calendar_ical_url")
    )

    db.save_run_header(run_id, planning_period, "started", input_hash)
    db.save_run_input(run_id, persisted_payload)
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
    google_calendar_warnings: list[str] = []

    if req.google_calendar_ical_url and req.google_calendar_ical_url.strip():
        try:
            remote_ics = fetch_google_calendar_ics(req.google_calendar_ical_url.strip())
        except GoogleCalendarFetchError as exc:
            google_calendar_warnings.append(str(exc))
            remote_ics = ""

        if remote_ics:
            hard_exclusions.extend(parse_hard_exclusions(remote_ics, None, window_start=start, window_end=end))

    hard_exclusions = _clip_to_window(hard_exclusions, start, end)

    partner_intervals = _clip_to_window(parse_result.intervals, start, end)
    user_exclusions = [i for i in partner_intervals if i.type in {"exclusion"}]
    kid_free_raw = [i for i in partner_intervals if i.type == "kid_free"]
    # Subtract partner exclusion periods from availability windows so that
    # couple-time coverage is not credited for dates Preet is unavailable.
    kid_free = _subtract_exclusions_from_kid_free(kid_free_raw, user_exclusions)
    all_exclusions = hard_exclusions + user_exclusions

    candidates = generate_candidates(
        start,
        end,
        handover_at=lambda handover_day: _handover_datetime(handover_day, runtime_config),
    )
    valid_candidates, constraint_audit = validate_candidates(
        candidates,
        all_exclusions,
        kid_free,
        partner_name=runtime_config.partner_name,
    )

    if not valid_candidates:
        result = PlanResultPayload(
            run_id=run_id,
            status="blocked",
            input_summary={
                "planning_period": planning_period,
                "holiday_start": str(req.holiday_start),
                "holiday_end": str(req.holiday_end),
                "timezone": "Europe/London",
            },
            parse_audit=[i.model_dump(mode="json") for i in partner_intervals],
            constraint_audit=constraint_audit,
            metadata={"input_hash": input_hash, "reason": "No valid candidates"},
        )
        if google_calendar_warnings:
            result.metadata["google_calendar_warnings"] = google_calendar_warnings
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
        parse_audit=[i.model_dump(mode="json") for i in (partner_intervals + hard_exclusions)],
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
