"""Integration test using real testdata fixtures from tests/testdata/."""
from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app

TESTDATA = Path(__file__).parent / "testdata"


def test_real_partner_text_parses_all_lines():
    """All 5 lines in partner_text.txt must parse without triggering clarification."""
    from app.services.interval_parser import parse_partner_text

    text = (TESTDATA / "partner_text.txt").read_text(encoding="utf-8")
    result = parse_partner_text(text, clarification_responses={})

    assert result.clarifications == [], (
        f"Unexpected clarification(s): {[c.raw_text for c in result.clarifications]}"
    )
    assert len(result.intervals) == 5

    types = [i.type for i in result.intervals]
    assert types.count("kid_free") == 4
    assert types.count("exclusion") == 1


def test_full_run_with_real_testdata_files():
    """End-to-end plan run using real partner text and iCal testdata."""
    client = TestClient(app)

    partner_text = (TESTDATA / "partner_text.txt").read_text(encoding="utf-8")
    ical_content = (TESTDATA / "calendar.ical").read_text(encoding="utf-8")

    payload = {
        "planning_period": "Summer Holidays",
        "holiday_start": "2026-07-20",
        "holiday_end": "2026-09-02",
        "partner_text": partner_text,
        "ical_content": ical_content,
        "pre_holiday_schoolday_confirmed": True,
        "options": {"boundary_policy": "Strict", "terminal_exception": False},
    }

    res = client.post("/plan/run", json=payload)
    assert res.status_code == 200

    body = res.json()["result"]
    assert body["status"] == "ok", (
        f"Expected ok, got {body['status']}. Clarifications: {body.get('clarifications')}"
    )

    # Primary and two alternatives must be present.
    assert body["primary"] is not None
    assert len(body["alternatives"]) == 2

    # All 5 partner text lines must have been parsed (no unresolved clarifications).
    assert body["clarifications"] == []

    # Constraint audit must have entries (candidates were scored).
    assert len(body["constraint_audit"]) > 0

    # iCal events from outside the holiday window (e.g. 2014–2018 calendar history)
    # must not appear in the parse audit.
    ical_entries = [e for e in body["parse_audit"] if e.get("source") == "ical"]
    for entry in ical_entries:
        start_year = int(entry["start"][:4])
        assert start_year >= 2026, f"Out-of-window iCal event leaked into audit: {entry}"

    # Partner-text intervals must be clipped to the holiday window.
    # The test fixture has a kidfree ending 2026-09-04 which is after holiday_end 2026-09-02.
    partner_entries = [e for e in body["parse_audit"] if e.get("source") == "partner_text"]
    for entry in partner_entries:
        assert entry["start"] >= "2026-07-20", f"Interval starts before window: {entry}"
        assert entry["end"]   <= "2026-09-03", f"Interval ends after window: {entry}"  # ISO sorts correctly

    # Artifacts must have been written to disk.
    assert Path(body["artifacts"]["json"]).exists()
    assert Path(body["artifacts"]["markdown"]).exists()
