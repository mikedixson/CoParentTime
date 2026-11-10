from __future__ import annotations

from datetime import date, datetime
from dataclasses import replace
import json
from pathlib import Path
import sqlite3

import pytest
from fastapi.testclient import TestClient

from app import config, db
from app.main import app
import app.services.app_service as app_service
from app.config import TIMEZONE
from app.config import RuntimeConfig
from app.services.candidate_generator import generate_candidates
from app.models import PlanRunRequest
from app.services.report_renderer import render_markdown


def test_home_includes_google_warning_banner_wiring():
    client = TestClient(app)

    res = client.get("/")
    assert res.status_code == 200
    html = res.text

    assert "<title>CoParentTime MVP</title>" in html
    assert "<h1>CoParentTime Local Planner</h1>" in html
    assert 'id="googleWarningBanner"' in html
    assert "function renderGoogleWarnings(result)" in html
    assert "renderGoogleWarnings(data.result);" in html


def test_run_and_fetch_plan_and_artifacts_exist():
    client = TestClient(app)

    payload = {
        "holiday_start": "2026-08-01",
        "holiday_end": "2026-08-21",
        "partner_text": "kidfree: 2026-08-03 18:00 to 2026-08-05 18:00\nexclude: 2026-08-10 to 2026-08-11",
        "pre_holiday_schoolday_confirmed": True,
        "options": {"boundary_policy": "Strict", "terminal_exception": False},
    }

    run_res = client.post("/plan/run", json=payload)
    assert run_res.status_code == 200
    run_body = run_res.json()

    run_id = run_body["result"]["run_id"]
    assert run_body["result"]["status"] == "ok"
    assert run_body["result"]["input_summary"]["planning_period"] == "2026-08-01 to 2026-08-21"
    assert "couple_time_views" in run_body["result"]
    assert "works" in run_body["result"]["couple_time_views"]
    assert "doesnt_work" in run_body["result"]["couple_time_views"]

    fetch_res = client.get(f"/plan/{run_id}")
    assert fetch_res.status_code == 200
    assert fetch_res.json()["result"]["run_id"] == run_id

    json_path = Path(run_body["result"]["artifacts"]["json"])
    md_path = Path(run_body["result"]["artifacts"]["markdown"])
    assert json_path.exists()
    assert md_path.exists()


def test_run_plan_pulls_google_calendar_tagged_hard_event(monkeypatch):
    client = TestClient(app)

    ics = """BEGIN:VCALENDAR
BEGIN:VEVENT
DTSTART:20260812T090000Z
DTEND:20260812T100000Z
    SUMMARY:[BLOCK] Google import test
END:VEVENT
END:VCALENDAR
"""

    monkeypatch.setattr(app_service, "fetch_google_calendar_ics", lambda url: ics)

    payload = {
        "holiday_start": "2026-08-01",
        "holiday_end": "2026-08-21",
        "partner_text": "kidfree: 2026-08-03 18:00 to 2026-08-05 18:00",
        "google_calendar_ical_url": "https://calendar.google.com/calendar/ical/test/basic.ics",
        "pre_holiday_schoolday_confirmed": True,
        "options": {"boundary_policy": "Strict", "terminal_exception": False},
    }

    run_res = client.post("/plan/run", json=payload)
    assert run_res.status_code == 200
    body = run_res.json()["result"]
    assert body["status"] == "ok"
    assert any("Google import test" in str(i.get("reason") or "") for i in body["parse_audit"])
    assert body["metadata"]["calendar_event_audit"]["google_hard_exclusions"] == 1
    assert body["metadata"]["calendar_event_audit"]["google_ignored_events"] == 0


def test_run_plan_ignores_untagged_google_calendar_event_by_default(monkeypatch):
    client = TestClient(app)

    ics = """BEGIN:VCALENDAR
BEGIN:VEVENT
DTSTART:20260812T090000Z
DTEND:20260812T100000Z
SUMMARY:Gmail auto flight event
END:VEVENT
END:VCALENDAR
"""

    monkeypatch.setattr(app_service, "fetch_google_calendar_ics", lambda url: ics)

    payload = {
        "holiday_start": "2026-08-01",
        "holiday_end": "2026-08-21",
        "partner_text": "kidfree: 2026-08-03 18:00 to 2026-08-05 18:00",
        "google_calendar_ical_url": "https://calendar.google.com/calendar/ical/test/basic.ics",
        "pre_holiday_schoolday_confirmed": True,
        "options": {"boundary_policy": "Strict", "terminal_exception": False},
    }

    run_res = client.post("/plan/run", json=payload)
    assert run_res.status_code == 200
    body = run_res.json()["result"]
    assert body["status"] == "ok"
    assert body["metadata"]["calendar_event_audit"]["google_hard_exclusions"] == 0
    assert body["metadata"]["calendar_event_audit"]["google_together_windows"] == 0
    assert body["metadata"]["calendar_event_audit"]["google_ignored_events"] == 1
    assert len(body["metadata"].get("google_ignored_events", [])) == 1


def test_run_plan_continues_when_google_calendar_unavailable(monkeypatch):
    client = TestClient(app)

    def _raise(_url: str) -> str:
        raise app_service.GoogleCalendarFetchError("network timeout")

    monkeypatch.setattr(app_service, "fetch_google_calendar_ics", _raise)

    payload = {
        "holiday_start": "2026-08-01",
        "holiday_end": "2026-08-21",
        "partner_text": "kidfree: 2026-08-03 18:00 to 2026-08-05 18:00",
        "google_calendar_ical_url": "https://calendar.google.com/calendar/ical/test/basic.ics",
        "pre_holiday_schoolday_confirmed": True,
        "options": {"boundary_policy": "Strict", "terminal_exception": False},
    }

    run_res = client.post("/plan/run", json=payload)
    assert run_res.status_code == 200
    body = run_res.json()["result"]
    assert body["status"] == "ok"
    assert "google_calendar_warnings" in body["metadata"]
    assert any("network timeout" in warning for warning in body["metadata"]["google_calendar_warnings"])


def test_run_plan_redacts_google_calendar_url_in_persisted_input(monkeypatch):
    client = TestClient(app)

    ics = """BEGIN:VCALENDAR
BEGIN:VEVENT
DTSTART:20260812T090000Z
DTEND:20260812T100000Z
SUMMARY:Google import test
END:VEVENT
END:VCALENDAR
"""

    monkeypatch.setattr(app_service, "fetch_google_calendar_ics", lambda url: ics)

    payload = {
        "holiday_start": "2026-08-01",
        "holiday_end": "2026-08-21",
        "partner_text": "",
        "google_calendar_ical_url": (
            "https://calendar.google.com/calendar/ical/my-calendar/private-token/basic.ics?nocache=123"
        ),
        "pre_holiday_schoolday_confirmed": True,
        "options": {"boundary_policy": "Strict", "terminal_exception": False},
    }

    run_res = client.post("/plan/run", json=payload)
    assert run_res.status_code == 200
    run_id = run_res.json()["result"]["run_id"]

    with sqlite3.connect(db.DB_PATH) as conn:
        row = conn.execute("SELECT payload_json FROM run_inputs WHERE run_id = ?", (run_id,)).fetchone()

    assert row is not None
    saved_payload = row[0]
    assert "private-token" not in saved_payload
    assert "nocache=123" not in saved_payload
    assert "***/basic.ics" in saved_payload


def test_weekend_pre_holiday_does_not_require_schoolday_confirmation():
    client = TestClient(app)

    payload = {
        "holiday_start": "2026-07-20",  # Monday, so pre-holiday date is Sunday.
        "holiday_end": "2026-08-01",
        "partner_text": "kidfree: 2026-07-25 10:00 to 2026-07-26 12:00",
        "pre_holiday_schoolday_confirmed": False,
        "options": {"boundary_policy": "Strict", "terminal_exception": False},
    }

    run_res = client.post("/plan/run", json=payload)
    assert run_res.status_code == 200
    body = run_res.json()["result"]
    assert body["status"] == "ok"
    assert body["clarifications"] == []


def test_weekday_pre_holiday_clarification_message_is_explicit(monkeypatch):
    client = TestClient(app)

    custom_runtime = RuntimeConfig(
        partner_name="Partner",
        school_holiday_ranges=(),
        partner_kid_free_ranges=(),
        google_calendar_ical_url=None,
        pre_holiday_school_pickup_time="15:45",
        schedule_visual_default="both",
    )
    monkeypatch.setattr(app_service, "get_runtime_config", lambda: custom_runtime)

    payload = {
        "holiday_start": "2026-07-21",  # Tuesday, so pre-holiday date is Monday.
        "holiday_end": "2026-08-01",
        "partner_text": "",
        "pre_holiday_schoolday_confirmed": False,
        "options": {"boundary_policy": "Strict", "terminal_exception": False},
    }

    run_res = client.post("/plan/run", json=payload)
    assert run_res.status_code == 200
    body = run_res.json()["result"]
    assert body["status"] == "needs_clarification"
    assert len(body["clarifications"]) == 1
    clarification = body["clarifications"][0]
    assert "2026-07-20" in clarification["prompt"]
    assert "Monday" in clarification["prompt"]
    assert "15:45" in clarification["prompt"]
    assert "15:45" in clarification["raw_text"]


def test_couple_time_reason_uses_configured_partner_name(monkeypatch):
    client = TestClient(app)

    custom_runtime = RuntimeConfig(
        partner_name="Alex",
        school_holiday_ranges=(),
        partner_kid_free_ranges=(),
        google_calendar_ical_url=None,
        pre_holiday_school_pickup_time="15:30",
        schedule_visual_default="both",
        partner_enabled=True,
    )
    monkeypatch.setattr(app_service, "get_runtime_config", lambda: custom_runtime)

    payload = {
        "holiday_start": "2026-08-01",
        "holiday_end": "2026-08-21",
        "partner_text": "kidfree: 2026-08-03 18:00 to 2026-08-05 18:00",
        "pre_holiday_schoolday_confirmed": True,
        "options": {"boundary_policy": "Strict", "terminal_exception": False},
    }

    run_res = client.post("/plan/run", json=payload)
    assert run_res.status_code == 200
    body = run_res.json()["result"]
    assert body["status"] == "ok"

    primary = body["primary"]
    assert primary is not None
    outcomes = primary["couple_time_window_outcomes"]
    assert len(outcomes) > 0
    assert any("Alex" in o["reason"] for o in outcomes)


def test_partner_text_is_ignored_when_partner_feature_disabled(monkeypatch):
    client = TestClient(app)

    custom_runtime = RuntimeConfig(
        partner_name="Alex",
        school_holiday_ranges=(),
        partner_kid_free_ranges=(),
        google_calendar_ical_url=None,
        pre_holiday_school_pickup_time="15:30",
        schedule_visual_default="both",
        partner_enabled=False,
    )
    monkeypatch.setattr(app_service, "get_runtime_config", lambda: custom_runtime)

    payload = {
        "holiday_start": "2026-08-01",
        "holiday_end": "2026-08-21",
        "partner_text": "kidfree: 2026-08-03 18:00 to 2026-08-05 18:00",
        "pre_holiday_schoolday_confirmed": True,
        "options": {"boundary_policy": "Strict", "terminal_exception": False},
    }

    run_res = client.post("/plan/run", json=payload)
    assert run_res.status_code == 200
    body = run_res.json()["result"]
    assert body["status"] == "ok"

    primary = body["primary"]
    assert primary is not None
    assert primary["couple_time_window_outcomes"] == []


def test_generate_candidates_use_default_and_override_handover_times():
    def handover_at(handover_day: date) -> datetime:
        override_times = {
            date(2026, 8, 8): "17:00",
        }
        value = override_times.get(handover_day, "13:00")
        hour, minute = value.split(":", maxsplit=1)
        return datetime(
            handover_day.year,
            handover_day.month,
            handover_day.day,
            int(hour),
            int(minute),
            tzinfo=TIMEZONE,
        )

    candidates = generate_candidates(
        handover_at(date(2026, 8, 1)),
        handover_at(date(2026, 8, 21)),
        handover_at=handover_at,
    )

    first_blocks = candidates[0].blocks
    assert first_blocks[0].start.isoformat() == "2026-08-01T13:00:00+01:00"
    assert first_blocks[0].end.isoformat() == "2026-08-08T17:00:00+01:00"
    assert first_blocks[1].start.isoformat() == "2026-08-08T17:00:00+01:00"
    assert first_blocks[1].end.isoformat() == "2026-08-15T13:00:00+01:00"


def test_ical_endpoint_returns_ics_for_valid_run():
    client = TestClient(app)

    payload = {
        "holiday_start": "2026-08-01",
        "holiday_end": "2026-08-21",
        "pre_holiday_schoolday_confirmed": True,
        "options": {"boundary_policy": "Strict", "terminal_exception": False},
    }

    run_res = client.post("/plan/run", json=payload)
    assert run_res.status_code == 200
    run_id = run_res.json()["result"]["run_id"]

    ical_res = client.get(f"/plan/{run_id}/ical")
    assert ical_res.status_code == 200
    assert ical_res.headers["content-type"].startswith("text/calendar")
    assert "attachment" in ical_res.headers.get("content-disposition", "")
    body = ical_res.text
    assert "BEGIN:VCALENDAR" in body
    assert "BEGIN:VEVENT" in body
    assert "DTSTART:" in body
    assert "DTEND:" in body
    assert "END:VCALENDAR" in body


def test_ical_endpoint_404_for_unknown_run():
    client = TestClient(app)
    res = client.get("/plan/nonexistent-run-id/ical")
    assert res.status_code == 404


def test_ical_endpoint_with_explicit_plan_id():
    client = TestClient(app)

    payload = {
        "holiday_start": "2026-08-01",
        "holiday_end": "2026-08-21",
        "pre_holiday_schoolday_confirmed": True,
        "options": {"boundary_policy": "Strict", "terminal_exception": False},
    }

    run_res = client.post("/plan/run", json=payload)
    assert run_res.status_code == 200
    body = run_res.json()["result"]
    run_id = body["run_id"]
    plan_id = body["primary"]["plan_id"]

    ical_res = client.get(f"/plan/{run_id}/ical?plan_id={plan_id}")
    assert ical_res.status_code == 200
    text = ical_res.text
    assert "BEGIN:VCALENDAR" in text
    assert "BEGIN:VEVENT" in text
    assert plan_id in text


def test_home_includes_calendar_export_wiring():
    client = TestClient(app)

    res = client.get("/")
    assert res.status_code == 200
    html = res.text

    assert "calendarExportButtons" in html
    assert "btn-ical-download" in html
    assert "btn-gcal-subscribe" in html
    assert "Download .ics" in html
    assert "Add to Google Calendar" in html


def test_home_includes_schedule_copy_image_and_print_wiring():
    client = TestClient(app)

    res = client.get("/")
    assert res.status_code == 200
    html = res.text

    assert "scheduleActionButtons" in html
    assert "copyScheduleToClipboard" in html
    assert "copyScheduleCardAsImage" in html
    assert "scheduleCardImageBlob" in html
    assert "printScheduleCard" in html
    assert 'data-schedule-action="copy"' in html
    assert 'data-schedule-action="copy-image"' in html
    assert 'data-schedule-action="print"' in html
    plain_copy = html.split("function scheduleClipboardPlainText(plan) {", 1)[1].split(
        "\n    function scheduleClipboardHtml", 1
    )[0]
    assert "Block ${i + 1}:" in plain_copy
    assert "sections.join('\\n\\n')" in plain_copy
    assert "Couple-time status:" not in plain_copy
    assert "Fairness gap:" not in plain_copy
    assert "Score:" not in plain_copy
    assert "scheduleClipboardChristmasLines(plan)" in html
    clipboard_html = html.split("function scheduleClipboardHtml(plan) {", 1)[1].split(
        "\n    async function copyScheduleToClipboard", 1
    )[0]
    assert "Block ${i + 1}:" in clipboard_html
    assert "Couple-time status:" not in clipboard_html
    assert "Fairness gap:" not in clipboard_html
    assert "CoParentTime schedule" not in clipboard_html


@pytest.mark.parametrize("legacy_labels", [False, True])
@pytest.mark.parametrize("parent,label", [("this_parent", "Parent A"), ("other_parent", "Parent B"), (None, None)])
def test_following_weekend_saved_in_api_artifacts_and_config_labels(tmp_path, monkeypatch, legacy_labels, parent, label):
    settings = tmp_path / "settings.json"
    keys = ("dad_title", "mum_title") if legacy_labels else ("this_parent", "other_parent")
    settings.write_text(json.dumps({keys[0]: "Parent A", keys[1]: "Parent B"}), encoding="utf-8")
    monkeypatch.setattr(config, "LOCAL_CONFIG_PATH", settings)
    config.get_runtime_config.cache_clear()
    try:
        client = TestClient(app)
        response = client.post("/plan/run", json={
            "holiday_start": "2026-08-01",
            "holiday_end": "2026-08-21",
            "pre_holiday_schoolday_confirmed": True,
            "following_weekend_parent": parent,
        })
        assert response.status_code == 200
        result = response.json()["result"]
        assert result["status"] == "ok"
        expected = {"start": "2026-08-28", "end": "2026-08-30", "parent": parent, "parent_label": label}
        assert result["following_weekend"] == expected

        # A saved result must keep its original name even after configuration changes.
        monkeypatch.setattr(app_service, "get_runtime_config", lambda: replace(
            config.get_runtime_config(), dad_title="Changed A", mum_title="Changed B",
        ))
        assert client.get(f"/plan/{result['run_id']}").json()["result"]["following_weekend"] == expected
        artifact = json.loads(Path(result["artifacts"]["json"]).read_text(encoding="utf-8"))
        assert artifact["following_weekend"] == expected
        report = Path(result["artifacts"]["markdown"]).read_text(encoding="utf-8")
        assert f"Friday 2026-08-28 to Sunday 2026-08-30: {label or 'Not specified'}." in report
        with sqlite3.connect(db.DB_PATH) as conn:
            row = conn.execute("SELECT payload_json FROM run_inputs WHERE run_id = ?", (result["run_id"],)).fetchone()
        assert json.loads(row[0])["following_weekend_parent"] == parent
    finally:
        config.get_runtime_config.cache_clear()


@pytest.mark.parametrize("end,friday,sunday", [
    ("2026-08-17", "2026-08-21", "2026-08-23"),
    ("2026-08-18", "2026-08-21", "2026-08-23"),
    ("2026-08-19", "2026-08-21", "2026-08-23"),
    ("2026-08-20", "2026-08-21", "2026-08-23"),
    ("2026-08-21", "2026-08-28", "2026-08-30"),
    ("2026-08-22", "2026-08-28", "2026-08-30"),
    ("2026-08-23", "2026-08-28", "2026-08-30"),
    ("2026-08-31", "2026-09-04", "2026-09-06"),
    ("2026-12-31", "2027-01-01", "2027-01-03"),
    ("2026-03-26", "2026-03-27", "2026-03-29"),
    ("2026-10-22", "2026-10-23", "2026-10-25"),
])
def test_following_weekend_dates(end, friday, sunday):
    request = PlanRunRequest(holiday_start=end, holiday_end=end)
    context = app_service._following_weekend_context(request, config.get_runtime_config())
    assert context.start.isoformat() == friday
    assert context.end.isoformat() == sunday
    assert context.parent is None
    assert context.parent_label is None


def test_following_weekend_is_informational_and_calendar_events_unchanged(monkeypatch):
    runtime = replace(config.get_runtime_config(), partner_enabled=False)
    monkeypatch.setattr(app_service, "get_runtime_config", lambda: runtime)
    client = TestClient(app)
    results = []
    calendars = []
    for parent in (None, "this_parent", "other_parent"):
        payload = {
            "holiday_start": "2026-08-01", "holiday_end": "2026-08-21",
            "pre_holiday_schoolday_confirmed": True,
        }
        if parent:
            payload["following_weekend_parent"] = parent
        response = client.post("/plan/run", json=payload)
        assert response.status_code == 200
        result = response.json()["result"]
        assert result["status"] == "ok"
        results.append(result)
        calendar = client.get(f"/plan/{result['run_id']}/ical").text
        calendars.append([line for line in calendar.splitlines() if not line.startswith(("UID:", "DTSTAMP:"))])
        assert calendar.count("BEGIN:VEVENT") == len(result["primary"]["blocks"])
        assert "20260828" not in calendar
    assert results[0]["following_weekend"]["parent"] is None
    for key in ("primary", "alternatives", "couple_time_views", "constraint_audit", "relationship_optimization_audit"):
        assert results[0][key] == results[1][key] == results[2][key]
    assert calendars[0] == calendars[1] == calendars[2]


@pytest.mark.parametrize("status", ["needs_clarification", "blocked"])
def test_following_weekend_context_in_non_success_results(monkeypatch, status):
    if status == "blocked":
        monkeypatch.setattr(app_service, "validate_candidates", lambda *args, **kwargs: ([], []))
    client = TestClient(app)
    response = client.post("/plan/run", json={
        "holiday_start": "2026-08-01", "holiday_end": "2026-08-21",
        "pre_holiday_schoolday_confirmed": status == "blocked",
        "following_weekend_parent": "other_parent",
    })
    assert response.status_code == 200
    result = response.json()["result"]
    assert result["status"] == status
    assert result["following_weekend"]["parent"] == "other_parent"
    assert result["following_weekend"]["start"] == "2026-08-28"
    assert client.get(f"/plan/{result['run_id']}").json()["result"]["following_weekend"] == result["following_weekend"]


def test_following_weekend_invalid_parent_is_rejected():
    response = TestClient(app).post("/plan/run", json={
        "holiday_start": "2026-08-01", "holiday_end": "2026-08-21",
        "following_weekend_parent": "Dad",
    })
    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", "following_weekend_parent"]


def test_historical_result_without_following_weekend_remains_readable():
    from app.models import PlanResultPayload

    old_result = {"run_id": "old-run", "status": "blocked", "input_summary": {}, "parse_audit": []}
    db.save_result("old-run", old_result)
    response = TestClient(app).get("/plan/old-run")
    assert response.status_code == 200
    assert response.json()["result"]["following_weekend"] is None
    assert "Following Weekend" not in render_markdown(PlanResultPayload.model_validate(old_result))


def test_home_includes_unselected_following_weekend_control_and_sharing():
    html = TestClient(app).get("/").text
    assert 'value="this_parent"' in html
    assert 'value="other_parent"' in html
    assert 'value="this_parent" checked' not in html
    assert 'value="other_parent" checked' not in html
    assert 'following_weekend_parent: fd.get(' in html
    assert "configureFollowingWeekend();" in html
    assert "followingWeekendText(savedFollowingWeekend)," in html
    assert html.count("${followingWeekendNote(savedFollowingWeekend)}") == 2
    assert "Information only; does not specify care before that Friday." not in html
