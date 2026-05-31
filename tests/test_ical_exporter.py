from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from app.models import CandidatePlan, ParentingBlock, PlanResultPayload
from app.services.ical_exporter import generate_plan_ics

TIMEZONE = ZoneInfo("Europe/London")


def _make_block(owner: str, start: str, end: str) -> ParentingBlock:
    return ParentingBlock(
        start=datetime.fromisoformat(start).replace(tzinfo=TIMEZONE),
        end=datetime.fromisoformat(end).replace(tzinfo=TIMEZONE),
        length_days=7,
        owner=owner,
    )


def _make_plan(plan_id: str, blocks: list[ParentingBlock]) -> CandidatePlan:
    return CandidatePlan(
        plan_id=plan_id,
        blocks=blocks,
        fairness_gap_days=0.0,
        overlap_hours=0.0,
        transitions=len(blocks) - 1,
        fragmentation=0,
    )


def _make_result(primary: CandidatePlan | None = None) -> PlanResultPayload:
    return PlanResultPayload(
        run_id="test-run-id",
        status="ok",
        input_summary={"planning_period": "2026-08-01 to 2026-08-21"},
        parse_audit=[],
        primary=primary,
    )


def test_generate_plan_ics_returns_valid_vcalendar():
    blocks = [
        _make_block("Dad", "2026-08-01T13:00:00", "2026-08-11T13:00:00"),
        _make_block("Mum", "2026-08-11T13:00:00", "2026-08-21T13:00:00"),
    ]
    plan = _make_plan("plan-A", blocks)
    result = _make_result(primary=plan)

    ics = generate_plan_ics(result)

    assert ics.startswith("BEGIN:VCALENDAR")
    assert "END:VCALENDAR" in ics
    assert ics.count("BEGIN:VEVENT") == 2
    assert ics.count("END:VEVENT") == 2


def test_generate_plan_ics_contains_correct_timestamps():
    blocks = [
        _make_block("Dad", "2026-08-01T13:00:00", "2026-08-11T13:00:00"),
    ]
    plan = _make_plan("plan-B", blocks)
    result = _make_result(primary=plan)

    ics = generate_plan_ics(result)

    # BST is UTC+1, so 13:00 BST == 12:00 UTC
    assert "DTSTART:20260801T120000Z" in ics
    assert "DTEND:20260811T120000Z" in ics


def test_generate_plan_ics_uses_primary_when_plan_id_is_none():
    blocks = [_make_block("Dad", "2026-08-01T13:00:00", "2026-08-11T13:00:00")]
    primary = _make_plan("primary-plan", blocks)
    result = _make_result(primary=primary)

    ics = generate_plan_ics(result, plan_id=None)

    assert "primary-plan" in ics


def test_generate_plan_ics_resolves_plan_by_id_from_alternatives():
    primary_blocks = [_make_block("Dad", "2026-08-01T13:00:00", "2026-08-11T13:00:00")]
    alt_blocks = [_make_block("Mum", "2026-08-01T13:00:00", "2026-08-11T13:00:00")]
    primary = _make_plan("primary-plan", primary_blocks)
    alt = _make_plan("alt-plan", alt_blocks)

    result = _make_result(primary=primary)
    result = result.model_copy(update={"alternatives": [alt]})

    ics = generate_plan_ics(result, plan_id="alt-plan")

    assert "alt-plan" in ics
    assert "SUMMARY:Mum parenting block" in ics


def test_generate_plan_ics_falls_back_to_primary_for_unknown_plan_id():
    blocks = [_make_block("Dad", "2026-08-01T13:00:00", "2026-08-11T13:00:00")]
    primary = _make_plan("primary-plan", blocks)
    result = _make_result(primary=primary)

    ics = generate_plan_ics(result, plan_id="nonexistent-plan-id")

    assert "primary-plan" in ics


def test_generate_plan_ics_empty_when_no_plan():
    result = _make_result(primary=None)

    ics = generate_plan_ics(result)

    assert "BEGIN:VCALENDAR" in ics
    assert "END:VCALENDAR" in ics
    assert "BEGIN:VEVENT" not in ics


def test_generate_plan_ics_includes_calendar_name():
    blocks = [_make_block("Dad", "2026-08-01T13:00:00", "2026-08-11T13:00:00")]
    plan = _make_plan("plan-A", blocks)
    result = _make_result(primary=plan)

    ics = generate_plan_ics(result)

    assert "X-WR-CALNAME:CoParenTime: 2026-08-01 to 2026-08-21" in ics


def test_generate_plan_ics_uses_crlf_line_endings():
    blocks = [_make_block("Dad", "2026-08-01T13:00:00", "2026-08-11T13:00:00")]
    plan = _make_plan("plan-A", blocks)
    result = _make_result(primary=plan)

    ics = generate_plan_ics(result)

    assert "\r\n" in ics
