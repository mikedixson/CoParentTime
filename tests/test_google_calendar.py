from __future__ import annotations

from urllib.error import HTTPError

from app.services import google_calendar


class _FakeResponse:
    def __init__(self, payload: bytes):
        self._payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self) -> bytes:
        return self._payload


def test_fetch_google_calendar_uses_direct_ics_url(monkeypatch):
    called = {"url": ""}

    def _fake_urlopen(request, timeout):
        called["url"] = request.full_url
        return _FakeResponse(
            b"BEGIN:VCALENDAR\nBEGIN:VEVENT\nDTSTART:20260805T090000Z\nDTEND:20260805T100000Z\nEND:VEVENT\nEND:VCALENDAR"
        )

    monkeypatch.setattr(google_calendar, "urlopen", _fake_urlopen)

    ics_link = "https://calendar.google.com/calendar/ical/private-token/basic.ics"
    text = google_calendar.fetch_google_calendar_ics(ics_link)

    assert "BEGIN:VCALENDAR" in text
    assert called["url"] == ics_link


def test_fetch_google_calendar_rejects_cid_share_link_for_private_use():
    share_link = "https://calendar.google.com/calendar/u/0?cid=synthetic-calendar-id"

    try:
        google_calendar.fetch_google_calendar_ics(share_link)
        assert False, "Expected GoogleCalendarFetchError"
    except google_calendar.GoogleCalendarFetchError as exc:
        message = str(exc)
        assert "do not include private iCal credentials" in message
        assert "Secret address in iCal format" in message


def test_fetch_google_calendar_errors_with_secret_ical_guidance(monkeypatch):
    def _fake_urlopen(_request, timeout=None):
        return _FakeResponse(b"<html>Not an iCal feed</html>")

    monkeypatch.setattr(google_calendar, "urlopen", _fake_urlopen)

    direct_ics = "https://calendar.google.com/calendar/ical/private-token/basic.ics"

    try:
        google_calendar.fetch_google_calendar_ics(direct_ics)
        assert False, "Expected GoogleCalendarFetchError"
    except google_calendar.GoogleCalendarFetchError as exc:
        message = str(exc)
        assert "not a valid VCALENDAR payload" in message
        assert "Secret address in iCal format" in message


def test_fetch_google_calendar_404_has_actionable_guidance(monkeypatch):
    def _fake_urlopen(_request, timeout=None):
        raise HTTPError(
            url="https://calendar.google.com/calendar/ical/private-token/basic.ics",
            code=404,
            msg="Not Found",
            hdrs=None,
            fp=None,
        )

    monkeypatch.setattr(google_calendar, "urlopen", _fake_urlopen)

    direct_ics = "https://calendar.google.com/calendar/ical/private-token/basic.ics"

    try:
        google_calendar.fetch_google_calendar_ics(direct_ics)
        assert False, "Expected GoogleCalendarFetchError"
    except google_calendar.GoogleCalendarFetchError as exc:
        message = str(exc)
        assert "404 Not Found" in message
        assert "Secret address in iCal format" in message


def test_fetch_google_calendar_rejects_non_google_hostname():
    bad_url = "https://notgoogle.com/calendar/u/0?cid=synthetic-calendar-id"

    try:
        google_calendar.fetch_google_calendar_ics(bad_url)
        assert False, "Expected GoogleCalendarFetchError"
    except google_calendar.GoogleCalendarFetchError as exc:
        assert "must point to a Google host" in str(exc)


def test_redact_google_calendar_url_masks_path_token_and_query_values():
    raw = "https://calendar.google.com/calendar/ical/my-calendar/private-token/basic.ics?nocache=123&cid=abc"

    redacted = google_calendar.redact_google_calendar_url(raw)

    assert redacted == "https://calendar.google.com/calendar/ical/my-calendar/***/basic.ics?cid=%2A%2A%2A&nocache=%2A%2A%2A"


def test_redact_google_calendar_url_masks_short_ical_token_path():
    raw = "https://calendar.google.com/calendar/ical/private-token/basic.ics?nocache=123"

    redacted = google_calendar.redact_google_calendar_url(raw)

    assert redacted == "https://calendar.google.com/calendar/ical/***/basic.ics?nocache=%2A%2A%2A"
