from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timedelta
import json
from pathlib import Path
import sqlite3

import pytest
from fastapi.testclient import TestClient

from app import config, db
from app.config import ParsedHandoverTimeOverride, RuntimeConfig, TIMEZONE
from app.main import app
from app.models import PlanResultPayload, PlanRunRequest
import app.services.app_service as service
from app.services.constraint_engine import parent_covering_window


@pytest.fixture
def christmas_runtime(monkeypatch):
    runtime = RuntimeConfig(
        partner_name="Partner",
        school_holiday_ranges=(),
        partner_kid_free_ranges=(),
        google_calendar_ical_url=None,
        pre_holiday_school_pickup_time="15:30",
        schedule_visual_default="both",
        christmas_split_date="12-26",
        dad_title="Parent A",
        mum_title="Parent B",
    )
    monkeypatch.setattr(service, "get_runtime_config", lambda: runtime)
    return runtime


def _payload(**changes):
    return {
        "holiday_start": "2026-12-19",
        "holiday_end": "2027-01-03",
        "pre_holiday_schoolday_confirmed": True,
        **changes,
    }


def _run(**changes):
    response = TestClient(app).post("/plan/run", json=_payload(**changes))
    assert response.status_code == 200
    return response.json()["result"]


@pytest.mark.parametrize("value", [None, "12-26", "12-01", "12-31", "01-01", "01-31"])
def test_christmas_config_valid_dates(tmp_path, monkeypatch, value):
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"christmas_split_date": value}), encoding="utf-8")
    monkeypatch.setattr(config, "LOCAL_CONFIG_PATH", path)
    config.get_runtime_config.cache_clear()
    try:
        assert config.get_runtime_config().christmas_split_date == value
        assert config.get_ui_config()["christmas_split_date"] == value
    finally:
        config.get_runtime_config.cache_clear()


@pytest.mark.parametrize("value", ["", "12-32", "01-00", "02-28", "2026-12-26", "12-6", 1226, False, {}, []])
def test_christmas_config_rejects_invalid_values(tmp_path, monkeypatch, value):
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"christmas_split_date": value}), encoding="utf-8")
    monkeypatch.setattr(config, "LOCAL_CONFIG_PATH", path)
    config.get_runtime_config.cache_clear()
    try:
        with pytest.raises(ValueError, match="christmas_split_date"):
            config.get_runtime_config()
    finally:
        config.get_runtime_config.cache_clear()


def test_christmas_config_absent_is_opt_in(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "LOCAL_CONFIG_PATH", tmp_path / "missing.json")
    config.get_runtime_config.cache_clear()
    try:
        assert config.get_runtime_config().christmas_split_date is None
    finally:
        config.get_runtime_config.cache_clear()


def test_configured_christmas_has_two_distinct_contiguous_candidates(christmas_runtime):
    first = _run()
    second = _run()
    assert first["status"] == "ok"
    assert first["input_summary"]["candidate_count"] == 2
    assert first["input_summary"]["feasible_count"] == 2
    assert first["christmas"]["requested_parent"] is None
    assert first["christmas"]["split_at"] == "2026-12-26T13:00:00Z"
    candidates = [first["primary"], *first["alternatives"]]
    assert len(candidates) == 2
    assert {candidate["christmas_day_parent"] for candidate in candidates} == {"this_parent", "other_parent"}
    for candidate in candidates:
        a, b = candidate["blocks"]
        assert a["start"] == "2026-12-19T13:00:00Z"
        assert a["end"] == b["start"] == "2026-12-26T13:00:00Z"
        assert b["end"] == "2027-01-03T13:00:00Z"
        assert a["owner"] != b["owner"]
        assert candidate["fairness_gap_days"] == 1
        assert candidate["transitions"] == 1
        assert candidate["fragmentation"] == 0
    assert first["primary"] == second["primary"]
    assert first["alternatives"] == second["alternatives"]


@pytest.mark.parametrize("split,expected", [("12-27", "2026-12-27"), ("01-01", "2027-01-01")])
def test_christmas_split_year_and_time_override(christmas_runtime, monkeypatch, split, expected):
    runtime = replace(
        christmas_runtime, christmas_split_date=split, default_handover_time="10:15",
        handover_time_overrides=(ParsedHandoverTimeOverride(date.fromisoformat(expected), "17:45"),),
    )
    monkeypatch.setattr(service, "get_runtime_config", lambda: runtime)
    result = _run()
    assert result["status"] == "ok"
    assert result["christmas"]["split_at"] == f"{expected}T17:45:00Z"
    assert result["primary"]["blocks"][0]["end"] == f"{expected}T17:45:00Z"


@pytest.mark.parametrize("parent,owner,label", [
    ("this_parent", "Dad", "Parent A"), ("other_parent", "Mum", "Parent B"),
])
@pytest.mark.parametrize("split", ["12-24", "12-26", None])
def test_manual_christmas_parent_owns_whole_day_in_every_output(
    christmas_runtime, monkeypatch, parent, owner, label, split,
):
    runtime = replace(christmas_runtime, christmas_split_date=split)
    monkeypatch.setattr(service, "get_runtime_config", lambda: runtime)
    result = _run(christmas_day_parent=parent, following_weekend_parent="other_parent")
    assert result["status"] == "ok"
    assert result["christmas"]["requested_parent_label"] == label
    assert result["following_weekend"]["parent"] == "other_parent"
    assert result["input_summary"]["candidate_count"] == (2 if split else 40)
    parsed = PlanResultPayload.model_validate(result)
    candidates = [parsed.primary, *parsed.alternatives, *parsed.couple_time_views["works"], *parsed.couple_time_views["doesnt_work"]]
    start = datetime(2026, 12, 25, tzinfo=TIMEZONE)
    for candidate in candidates:
        assert candidate is not None
        assert candidate.christmas_day_parent == parent
        assert parent_covering_window(candidate, start, start + timedelta(days=1)) == owner
        ical = TestClient(app).get(f"/plan/{result['run_id']}/ical", params={"plan_id": candidate.plan_id}).text
        assert ical.count("BEGIN:VEVENT") == len(candidate.blocks)
        assert "Christmas" not in ical
    assert any("Christmas Day constraint violated" in row["reason"] for row in result["constraint_audit"])
    assert json.loads(Path(result["artifacts"]["json"]).read_text(encoding="utf-8"))["christmas"] == result["christmas"]
    report = Path(result["artifacts"]["markdown"]).read_text(encoding="utf-8")
    assert f"Requested parent: {label}" in report
    assert f"Christmas Day parent: {label}" in report
    with sqlite3.connect(db.DB_PATH) as conn:
        raw = conn.execute("SELECT payload_json FROM run_inputs WHERE run_id = ?", (result["run_id"],)).fetchone()[0]
    assert json.loads(raw)["christmas_day_parent"] == parent
    monkeypatch.setattr(service, "get_runtime_config", lambda: replace(runtime, dad_title="New", mum_title="Changed"))
    assert TestClient(app).get(f"/plan/{result['run_id']}").json()["result"]["christmas"] == result["christmas"]


@pytest.mark.parametrize("available,expected", [
    ("2026-12-20 00:00 to 2026-12-24 23:00", "other_parent"),
    ("2026-12-28 00:00 to 2026-12-30 23:00", "this_parent"),
])
def test_automatic_order_uses_existing_couple_time_scoring(christmas_runtime, monkeypatch, available, expected):
    runtime = replace(christmas_runtime, partner_enabled=True)
    monkeypatch.setattr(service, "get_runtime_config", lambda: runtime)
    result = _run(partner_text=available)
    assert result["status"] == "ok"
    assert result["primary"]["christmas_day_parent"] == expected
    assert result["primary"]["overlap_hours"] > 0
    assert result["christmas"]["requested_parent"] is None


@pytest.mark.parametrize("split,start,end,reason", [
    ("12-19", "2026-12-19", "2027-01-03", "strictly inside"),
    ("01-03", "2026-12-19", "2027-01-03", "strictly inside"),
    ("01-04", "2026-12-19", "2027-01-03", "strictly inside"),
    ("12-25", "2026-12-19", "2027-01-03", "cannot divide Christmas Day"),
    ("12-26", "2026-12-25", "2027-01-03", "whole of 25 December"),
    ("12-26", "2026-12-19", "2026-12-25", "whole of 25 December"),
    ("12-26", "2025-12-19", "2027-01-03", "exactly one Christmas Day"),
])
def test_invalid_christmas_window_is_blocked_and_persisted(christmas_runtime, monkeypatch, split, start, end, reason):
    runtime = replace(christmas_runtime, christmas_split_date=split)
    monkeypatch.setattr(service, "get_runtime_config", lambda: runtime)
    result = _run(holiday_start=start, holiday_end=end)
    assert result["status"] == "blocked"
    assert reason in result["metadata"]["reason"]
    assert reason in result["constraint_audit"][0]["reason"]
    assert result["primary"] is None
    assert TestClient(app).get(f"/plan/{result['run_id']}").json()["result"]["christmas"] == result["christmas"]
    assert reason in Path(result["artifacts"]["markdown"]).read_text(encoding="utf-8")


@pytest.mark.parametrize("split,owner", [("12-25", "Mum"), ("12-26", "Dad")])
def test_exact_midnight_christmas_splits_are_valid(christmas_runtime, monkeypatch, split, owner):
    runtime = replace(
        christmas_runtime, christmas_split_date=split,
        handover_time_overrides=(ParsedHandoverTimeOverride(date.fromisoformat(f"2026-{split}"), "00:00"),),
    )
    monkeypatch.setattr(service, "get_runtime_config", lambda: runtime)
    result = _run()
    assert result["status"] == "ok"
    assert result["primary"]["blocks"][0]["owner"] == "Dad"
    assert result["primary"]["christmas_day_parent"] == ("this_parent" if owner == "Dad" else "other_parent")


def test_manual_selection_conflict_with_hard_calendar_exclusion_blocks(christmas_runtime):
    ical = "\r\n".join([
        "BEGIN:VCALENDAR", "VERSION:2.0", "BEGIN:VEVENT",
        "DTSTART:20261225T090000Z", "DTEND:20261225T100000Z",
        "SUMMARY:Unavailable", "END:VEVENT", "END:VCALENDAR",
    ])
    blocked = _run(christmas_day_parent="this_parent", ical_content=ical)
    assert blocked["status"] == "blocked"
    assert "No feasible Christmas schedule" in blocked["metadata"]["reason"]
    assert any("Hard exclusion" in row["reason"] for row in blocked["constraint_audit"])
    automatic = _run(ical_content=ical)
    assert automatic["status"] == "ok"
    assert automatic["primary"]["christmas_day_parent"] == "other_parent"


def test_unconfigured_and_non_christmas_plans_preserve_candidates(christmas_runtime, monkeypatch):
    runtime = replace(christmas_runtime, christmas_split_date=None)
    monkeypatch.setattr(service, "get_runtime_config", lambda: runtime)
    plain = _run()
    assert plain["christmas"] is None
    assert plain["input_summary"]["candidate_count"] == 40
    summer = _run(holiday_start="2026-08-01", holiday_end="2026-08-21")
    monkeypatch.setattr(service, "get_runtime_config", lambda: christmas_runtime)
    configured_summer = _run(holiday_start="2026-08-01", holiday_end="2026-08-21")
    assert configured_summer["christmas"] is None
    for key in ("primary", "alternatives", "couple_time_views", "constraint_audit"):
        assert summer[key] == configured_summer[key]
    invalid = _run(holiday_start="2026-08-01", holiday_end="2026-08-21", christmas_day_parent="this_parent")
    assert invalid["status"] == "blocked"
    assert "exactly one Christmas Day" in invalid["metadata"]["reason"]


@pytest.mark.parametrize("year", [2024, 2026, 2028])
def test_christmas_whole_day_window_boundaries_and_years(christmas_runtime, monkeypatch, year):
    runtime = replace(christmas_runtime, christmas_split_date=None, default_handover_time="00:00")
    monkeypatch.setattr(service, "get_runtime_config", lambda: runtime)
    whole_day = _run(
        holiday_start=f"{year}-12-25", holiday_end=f"{year}-12-26",
        christmas_day_parent="other_parent",
    )
    assert whole_day["status"] == "ok"
    assert whole_day["christmas"]["christmas_day"] == f"{year}-12-25"
    outside = _run(
        holiday_start=f"{year}-12-19", holiday_end=f"{year}-12-25",
        christmas_day_parent="this_parent",
    )
    assert outside["status"] == "blocked"
    assert "exactly one Christmas Day" in outside["metadata"]["reason"]


def test_christmas_context_in_clarification_and_legacy_results(christmas_runtime):
    result = _run(pre_holiday_schoolday_confirmed=False)
    assert result["status"] == "needs_clarification"
    assert result["christmas"]["split_at"] == "2026-12-26T13:00:00Z"
    assert TestClient(app).get(f"/plan/{result['run_id']}").json()["result"]["christmas"] == result["christmas"]
    old = PlanResultPayload.model_validate({"run_id": "old", "status": "blocked", "input_summary": {}, "parse_audit": []})
    assert old.christmas is None
    assert PlanRunRequest.model_validate(_payload()).christmas_day_parent is None
    response = TestClient(app).post("/plan/run", json=_payload(christmas_day_parent="Dad"))
    assert response.status_code == 422


def test_home_christmas_control_and_saved_output_wiring(christmas_runtime, monkeypatch):
    monkeypatch.setattr(config, "get_runtime_config", lambda: christmas_runtime)
    html = TestClient(app).get("/").text
    assert 'id="christmasControl"' in html
    assert 'name="christmas_day_parent" value="this_parent" />' in html
    assert 'name="christmas_day_parent" value="other_parent" />' in html
    assert "configureChristmasControl();" in html
    assert "christmas_day_parent: fd.get('christmas_day_parent') || null" in html
    assert "const text = christmasText(savedChristmas, plan);" in html
    assert html.count("const christmasLines = scheduleClipboardChristmasLines(plan)") == 2
    assert "${christmasNote(savedChristmas, plan)}" in html
    assert "html += christmasNote(savedChristmas);" in html
    assert "const boxingDay = boxingDayText(context, plan);" in html
    assert "Boxing Day parent:" in html
    assert "esc(result.metadata?.reason" in html


@pytest.mark.parametrize("parent,first,second", [
    ("this_parent", "Parent A", "Parent B"),
    ("other_parent", "Parent B", "Parent A"),
])
@pytest.mark.parametrize("split,handover,expected", [
    ("12-24", "13:00", "{first}"),
    ("12-26", "00:00", "{second}"),
    ("12-26", "10:00", "{second}"),
    ("12-26", "13:00", "{second}"),
    ("12-27", "13:00", "{first}"),
    ("01-01", "13:00", "{first}"),
])
def test_boxing_day_parent_in_reports(
    christmas_runtime, monkeypatch, parent, first, second, split, handover, expected,
):
    runtime = replace(christmas_runtime, christmas_split_date=split, default_handover_time=handover)
    monkeypatch.setattr(service, "get_runtime_config", lambda: runtime)
    result = _run(christmas_day_parent=parent)
    assert result["status"] == "ok"
    report = Path(result["artifacts"]["markdown"]).read_text(encoding="utf-8")
    note = f"Boxing Day parent: {expected.format(first=first, second=second)}"
    assert note in report.splitlines()
    candidate_count = 1 + len(result["alternatives"]) + sum(len(plans) for plans in result["couple_time_views"].values())
    assert report.count(note) == candidate_count


@pytest.mark.parametrize("handover,expected", [
    ("00:00", "Outside planned window"),
    ("13:00", "Parent A"),
])
def test_boxing_day_output_does_not_infer_care_outside_plan(christmas_runtime, monkeypatch, handover, expected):
    runtime = replace(christmas_runtime, christmas_split_date=None, default_handover_time=handover)
    monkeypatch.setattr(service, "get_runtime_config", lambda: runtime)
    result = _run(christmas_day_parent="this_parent", holiday_end="2026-12-26")
    assert result["status"] == "ok"
    report = Path(result["artifacts"]["markdown"]).read_text(encoding="utf-8")
    assert f"Boxing Day parent: {expected}" in report.splitlines()
