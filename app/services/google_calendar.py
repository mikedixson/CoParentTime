from __future__ import annotations

import base64
import binascii
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, quote, unquote, urlparse
from urllib.request import Request, urlopen


class GoogleCalendarFetchError(RuntimeError):
    pass


def _validate_google_calendar_url(url: str) -> str:
    parsed = urlparse(url.strip())
    if parsed.scheme not in {"http", "https"}:
        raise GoogleCalendarFetchError("Google Calendar URL must start with http:// or https://")
    hostname = (parsed.hostname or "").lower()
    allowed_hosts = {"calendar.google.com", "www.google.com", "google.com"}
    if hostname not in allowed_hosts and not hostname.endswith(".google.com"):
        raise GoogleCalendarFetchError("Google Calendar URL must point to a Google host")
    return url.strip()


def _decode_google_cid(cid: str) -> str:
    raw = unquote(cid.strip())
    if not raw:
        raise GoogleCalendarFetchError("Google Calendar share link is missing the cid value")

    # Google share links often encode calendar IDs in base64-url format.
    pad = "=" * ((4 - (len(raw) % 4)) % 4)
    try:
        decoded = base64.urlsafe_b64decode((raw + pad).encode("ascii")).decode("utf-8").strip()
    except (ValueError, UnicodeDecodeError, binascii.Error):
        decoded = ""

    return decoded or raw


def redact_google_calendar_url(url: str | None) -> str | None:
    if not url:
        return url

    raw = url.strip()
    if not raw:
        return None

    parsed = urlparse(raw)
    safe_query = ""
    if parsed.query:
        query = parse_qs(parsed.query, keep_blank_values=True)
        masked = {key: ["***"] * len(values) for key, values in query.items()}
        safe_query = "?" + "&".join(
            f"{quote(key, safe='')}={quote(value, safe='')}"
            for key, values in sorted(masked.items())
            for value in values
        )

    parts = [segment for segment in parsed.path.split("/") if segment]
    if "ical" in parts:
        ical_index = parts.index("ical")
        # Redact the segment immediately before the .ics filename. This handles
        # both short paths (/calendar/ical/<token>/basic.ics) and longer forms.
        if parts[-1].endswith(".ics") and (len(parts) - 2) > ical_index:
            masked_parts = parts.copy()
            masked_parts[-2] = "***"
            path = "/" + "/".join(masked_parts)
        else:
            path = parsed.path
    else:
        path = parsed.path

    if parsed.scheme and parsed.netloc:
        return f"{parsed.scheme}://{parsed.netloc}{path}{safe_query}"
    return f"{path}{safe_query}" or "***"


def _normalize_google_calendar_url(url: str) -> str:
    validated = _validate_google_calendar_url(url)
    parsed = urlparse(validated)

    if "/calendar/ical/" in parsed.path and parsed.path.endswith(".ics"):
        return validated

    query = parse_qs(parsed.query)
    cid_values = query.get("cid", [])
    if not cid_values:
        return validated

    # Validate/parse the cid format but do not expose decoded identifiers.
    _decode_google_cid(cid_values[0])
    raise GoogleCalendarFetchError(
        "Google share links with ?cid=... do not include private iCal credentials. "
        "For private calendars, use Settings and sharing > Integrate calendar > Secret address in iCal format."
    )


def fetch_google_calendar_ics(url: str, timeout_seconds: int = 8) -> str:
    target = _normalize_google_calendar_url(url)
    request = Request(target, headers={"User-Agent": "CoParenTime/1.0"})
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            raw = response.read()
    except HTTPError as exc:
        if exc.code == 404:
            raise GoogleCalendarFetchError(
                "Google Calendar returned 404 Not Found for the configured iCal URL. "
                "Re-copy the Secret address in iCal format from Google Calendar, and confirm "
                "the calendar is still shared and the URL is not a public share link."
            ) from exc
        raise GoogleCalendarFetchError(f"Unable to fetch Google Calendar iCal feed: {exc}") from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise GoogleCalendarFetchError(f"Unable to fetch Google Calendar iCal feed: {exc}") from exc

    text = raw.decode("utf-8", errors="replace").strip()
    if "BEGIN:VCALENDAR" not in text:
        raise GoogleCalendarFetchError(
            "Google Calendar response is not a valid VCALENDAR payload. "
            "If this is a private calendar, use Settings and sharing > Integrate calendar > Secret address in iCal format."
        )
    return text
