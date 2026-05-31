from __future__ import annotations

import json
from datetime import date

import pytest

from app import config


def test_runtime_config_preserves_raw_partner_text_lines(tmp_path, monkeypatch):
    local_config = tmp_path / "coparentime.local.json"
    local_config.write_text(
        json.dumps(
            {
                "partner_enabled": True,
                "partner_name": "Preet",
                "school_holiday_ranges": ["2026-07-20 - 2026-09-02"],
                "partner_kid_free_ranges": [
                    "kidfree: 2026-07-21 08:00 to 2026-07-22 09:00",
                    "exclude: 2026-08-26 to 2026-09-01",
                ],
                "google_calendar_ical_url": "https://calendar.google.com/calendar/ical/test/basic.ics",
                "pre_holiday_school_pickup_time": "15:35",
            }
        ),
        encoding="utf-8",
    )

    config.get_runtime_config.cache_clear()
    monkeypatch.setattr(config, "LOCAL_CONFIG_PATH", local_config)

    runtime = config.get_runtime_config()
    ui_config = config.get_ui_config()

    assert runtime.partner_enabled is True
    assert ui_config["partner_enabled"] is True
    assert runtime.partner_kid_free_ranges == (
        "kidfree: 2026-07-21 08:00 to 2026-07-22 09:00",
        "exclude: 2026-08-26 to 2026-09-01",
    )
    assert ui_config["partner_kid_free_ranges"] == [
        {"raw": "kidfree: 2026-07-21 08:00 to 2026-07-22 09:00"},
        {"raw": "exclude: 2026-08-26 to 2026-09-01"},
    ]
    assert runtime.google_calendar_ical_url == "https://calendar.google.com/calendar/ical/test/basic.ics"
    assert ui_config["google_calendar_ical_url"] == "https://calendar.google.com/calendar/ical/test/basic.ics"
    assert runtime.pre_holiday_school_pickup_time == "15:35"
    assert ui_config["pre_holiday_school_pickup_time"] == "15:35"

    config.get_runtime_config.cache_clear()


def test_runtime_config_accepts_named_school_holiday_ranges(tmp_path, monkeypatch):
    local_config = tmp_path / "coparentime.local.json"
    local_config.write_text(
        json.dumps(
            {
                "partner_name": "Preet",
                "school_holiday_ranges": ["summer holidays: 20/07/2026 - 02/09/2026"],
                "partner_kid_free_ranges": [],
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(config, "LOCAL_CONFIG_PATH", local_config)

    runtime = config.get_runtime_config()
    ui_config = config.get_ui_config()

    assert runtime.partner_enabled is False
    assert ui_config["partner_enabled"] is False
    assert len(runtime.school_holiday_ranges) == 1
    assert runtime.school_holiday_ranges[0].start.isoformat() == "2026-07-20"
    assert runtime.school_holiday_ranges[0].end.isoformat() == "2026-09-02"
    assert runtime.school_holiday_ranges[0].raw == "summer holidays: 20/07/2026 - 02/09/2026"
    assert ui_config["school_holiday_ranges"] == [
        {
            "raw": "summer holidays: 20/07/2026 - 02/09/2026",
            "start": "2026-07-20",
            "end": "2026-09-02",
        }
    ]

    config.get_runtime_config.cache_clear()


def test_runtime_config_defaults_pickup_time_when_not_set(tmp_path, monkeypatch):
    local_config = tmp_path / "coparentime.local.json"
    local_config.write_text(
        json.dumps(
            {
                "partner_name": "Preet",
                "school_holiday_ranges": ["2026-07-20 - 2026-09-02"],
                "partner_kid_free_ranges": [],
            }
        ),
        encoding="utf-8",
    )

    config.get_runtime_config.cache_clear()
    monkeypatch.setattr(config, "LOCAL_CONFIG_PATH", local_config)

    runtime = config.get_runtime_config()
    assert runtime.pre_holiday_school_pickup_time == "15:30"
    assert runtime.partner_enabled is False

    config.get_runtime_config.cache_clear()


@pytest.mark.parametrize("partner_enabled", ["disabled", "   "])
def test_runtime_config_defaults_invalid_partner_enabled_strings_to_false(tmp_path, monkeypatch, partner_enabled):
    local_config = tmp_path / "coparentime.local.json"
    local_config.write_text(
        json.dumps(
            {
                "partner_enabled": partner_enabled,
                "partner_name": "Preet",
                "school_holiday_ranges": ["2026-07-20 - 2026-09-02"],
                "partner_kid_free_ranges": [],
            }
        ),
        encoding="utf-8",
    )

    config.get_runtime_config.cache_clear()
    monkeypatch.setattr(config, "LOCAL_CONFIG_PATH", local_config)

    runtime = config.get_runtime_config()
    ui_config = config.get_ui_config()

    assert runtime.partner_enabled is False
    assert ui_config["partner_enabled"] is False

    config.get_runtime_config.cache_clear()


def test_runtime_config_parses_default_handover_time_and_overrides(tmp_path, monkeypatch):
    local_config = tmp_path / "coparentime.local.json"
    local_config.write_text(
        json.dumps(
            {
                "partner_name": "Preet",
                "school_holiday_ranges": ["2026-07-20 - 2026-09-02"],
                "partner_kid_free_ranges": [],
                "default_handover_time": "13:00",
                "handover_time_overrides": {
                    "20260808": "17:00",
                    "2026-08-15": "10:30"
                },
            }
        ),
        encoding="utf-8",
    )

    config.get_runtime_config.cache_clear()
    monkeypatch.setattr(config, "LOCAL_CONFIG_PATH", local_config)

    runtime = config.get_runtime_config()
    ui_config = config.get_ui_config()

    assert runtime.default_handover_time == "13:00"
    assert runtime.handover_time_for(date(2026, 8, 1)).strftime("%H:%M") == "13:00"
    assert runtime.handover_time_for(date(2026, 8, 8)).strftime("%H:%M") == "17:00"
    assert runtime.handover_time_for(date(2026, 8, 15)).strftime("%H:%M") == "10:30"
    assert ui_config["default_handover_time"] == "13:00"
    assert ui_config["handover_time_overrides"] == {
        "2026-08-08": "17:00",
        "2026-08-15": "10:30",
    }

    config.get_runtime_config.cache_clear()