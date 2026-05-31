from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
import sqlite3

from fastapi.testclient import TestClient

from app import db
from app.main import app
import app.services.app_service as app_service
from app.config import TIMEZONE
from app.config import RuntimeConfig
from app.services.candidate_generator import generate_candidates


def test_home_includes_google_warning_banner_wiring():
    client = TestClient(app)

    res = client.get("/")
    assert res.status_code == 200
    html = res.text

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


def test_run_plan_pulls_google_calendar_ical(monkeypatch):
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
        "partner_text": "kidfree: 2026-08-03 18:00 to 2026-08-05 18:00",
        "google_calendar_ical_url": "https://calendar.google.com/calendar/ical/test/basic.ics",
        "pre_holiday_schoolday_confirmed": True,
        "options": {"boundary_policy": "Strict", "terminal_exception": False},
    }

    run_res = client.post("/plan/run", json=payload)
    assert run_res.status_code == 200
    body = run_res.json()["result"]
    assert body["status"] == "ok"
    assert any(i.get("reason") == "Google import test" for i in body["parse_audit"])


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
