from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date, time
from functools import lru_cache
from pathlib import Path
from zoneinfo import ZoneInfo

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "coparentime.db"
ARTIFACTS_DIR = BASE_DIR / "artifacts"
TIMEZONE = ZoneInfo("Europe/London")
MIN_CANDIDATES = 20
MAX_RUNTIME_SECONDS = 10
LOCAL_CONFIG_PATH = BASE_DIR / "coparentime.local.json"

_RANGE_RE = re.compile(
	r"^\s*(\d{2}/\d{2}/\d{4}|\d{8}|\d{4}-\d{2}-\d{2})\s*-\s*(\d{2}/\d{2}/\d{4}|\d{8}|\d{4}-\d{2}-\d{2})\s*$"
)
_HEX_COLOR_RE = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$")
_RGB_COLOR_RE = re.compile(r"^rgba?\(\s*(?:\d{1,3}\s*,\s*){2}\d{1,3}(?:\s*,\s*(?:0|1|0?\.\d+))?\s*\)$")
_HSL_COLOR_RE = re.compile(r"^hsla?\(\s*\d{1,3}(?:\.\d+)?\s*,\s*\d{1,3}%\s*,\s*\d{1,3}%(?:\s*,\s*(?:0|1|0?\.\d+))?\s*\)$")
_NAME_COLOR_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9-]{0,31}$")


@dataclass(frozen=True)
class ParsedRange:
	start: date
	end: date
	raw: str


@dataclass(frozen=True)
class ParsedHandoverTimeOverride:
	day: date
	time_text: str


@dataclass(frozen=True)
class RuntimeConfig:
	partner_name: str
	school_holiday_ranges: tuple[ParsedRange, ...]
	partner_kid_free_ranges: tuple[str, ...]
	google_calendar_ical_url: str | None
	pre_holiday_school_pickup_time: str
	schedule_visual_default: str
	calendar_event_policy_default_mode: str = "ignore_untagged"
	calendar_event_policy_hard_tags: tuple[str, ...] = ("BLOCK", "UNAVAILABLE")
	calendar_event_policy_together_tags: tuple[str, ...] = ("TOGETHER",)
	partner_enabled: bool = False
	default_handover_time: str = "13:00"
	handover_time_overrides: tuple[ParsedHandoverTimeOverride, ...] = ()
	dad_title: str = "Dad"
	mum_title: str = "Mum"
	dad_color: str = "#0f766e"
	mum_color: str = "#b45309"
	partner_available_color: str = "#22c55e"
	partner_unavailable_color: str = "#f97316"
	christmas_split_date: str | None = None

	def handover_time_for(self, handover_day: date) -> time:
		for override in self.handover_time_overrides:
			if override.day == handover_day:
				return _hhmm_to_time(override.time_text)
		return _hhmm_to_time(self.default_handover_time)


def _parse_date_token(token: str) -> date:
	token = token.strip()
	if re.fullmatch(r"\d{8}", token):
		return date(int(token[0:4]), int(token[4:6]), int(token[6:8]))
	if re.fullmatch(r"\d{2}/\d{2}/\d{4}", token):
		return date(int(token[6:10]), int(token[3:5]), int(token[0:2]))
	if re.fullmatch(r"\d{4}-\d{2}-\d{2}", token):
		return date.fromisoformat(token)
	raise ValueError(f"Unsupported date token: {token}")


def _parse_range(raw: str) -> ParsedRange:
	range_text = raw
	if ":" in raw:
		_, _, maybe_range = raw.partition(":")
		if _RANGE_RE.match(maybe_range.strip()):
			range_text = maybe_range.strip()

	match = _RANGE_RE.match(range_text)
	if not match:
		raise ValueError(f"Unsupported date range format: {raw}")
	start = _parse_date_token(match.group(1))
	end = _parse_date_token(match.group(2))
	if end < start:
		raise ValueError(f"Range end before start: {raw}")
	return ParsedRange(start=start, end=end, raw=raw)


def _parse_range_list(values: list[str]) -> tuple[ParsedRange, ...]:
	parsed: list[ParsedRange] = []
	for raw in values:
		if not raw or not str(raw).strip():
			continue
		parsed.append(_parse_range(str(raw).strip()))
	return tuple(parsed)


def _parse_text_line_list(values: list[str]) -> tuple[str, ...]:
	parsed: list[str] = []
	for raw in values:
		if not raw or not str(raw).strip():
			continue
		parsed.append(str(raw).strip())
	return tuple(parsed)


def _parse_hhmm_time(raw: str | None, default: str = "15:30") -> str:
	value = str(raw or "").strip() or default
	if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", value):
		raise ValueError(f"Unsupported time format (expected HH:MM): {value}")
	return value


def _hhmm_to_time(value: str) -> time:
	hours, minutes = value.split(":", maxsplit=1)
	return time(hour=int(hours), minute=int(minutes))


def _parse_handover_time_overrides(raw: object) -> tuple[ParsedHandoverTimeOverride, ...]:
	if raw in (None, ""):
		return ()
	if not isinstance(raw, dict):
		raise ValueError("handover_time_overrides must be an object mapping dates to HH:MM values")

	parsed: list[ParsedHandoverTimeOverride] = []
	for raw_day, raw_time in raw.items():
		day = _parse_date_token(str(raw_day))
		time_text = _parse_hhmm_time(str(raw_time), default="13:00")
		parsed.append(ParsedHandoverTimeOverride(day=day, time_text=time_text))

	parsed.sort(key=lambda item: item.day)
	return tuple(parsed)


def _parse_schedule_visual_default(raw: str | None, default: str = "both") -> str:
	value = str(raw or "").strip().lower() or default
	if value not in {"timeline", "calendar", "both"}:
		return default
	return value


def _parse_christmas_split_date(raw: object) -> str | None:
	if raw is None:
		return None
	if not isinstance(raw, str) or not re.fullmatch(r"(12|01)-\d{2}", raw):
		raise ValueError("christmas_split_date must be a December or January date in MM-DD format, or null")
	try:
		date.fromisoformat(f"2000-{raw}")
	except ValueError as exc:
		raise ValueError("christmas_split_date must be a valid December or January date") from exc
	return raw


def _parse_nonempty_text(raw: str | None, default: str) -> str:
	value = str(raw or "").strip()
	return value or default


def _parse_bool(raw: object, default: bool = False) -> bool:
	if isinstance(raw, bool):
		return raw
	if isinstance(raw, str):
		value = raw.strip().lower()
		if value in {"1", "true", "yes", "on"}:
			return True
		if value in {"0", "false", "no", "off"}:
			return False
		return default
	if raw is None:
		return default
	return bool(raw)


def _parse_css_color(raw: str | None, default: str) -> str:
	value = str(raw or "").strip()
	if not value:
		return default
	if _HEX_COLOR_RE.fullmatch(value):
		return value
	if _RGB_COLOR_RE.fullmatch(value):
		return value
	if _HSL_COLOR_RE.fullmatch(value):
		return value
	if _NAME_COLOR_RE.fullmatch(value):
		return value
	return default


def _parse_calendar_default_mode(raw: object, default: str = "ignore_untagged") -> str:
	value = str(raw or "").strip().lower()
	if value in {"ignore_untagged", "hard_untagged"}:
		return value
	return default


def _parse_tag_list(raw: object, default: tuple[str, ...]) -> tuple[str, ...]:
	if raw is None:
		return default
	if isinstance(raw, str):
		items = [x.strip() for x in raw.split(",") if x and x.strip()]
	else:
		items = [str(x).strip() for x in list(raw) if str(x).strip()] if isinstance(raw, (list, tuple)) else []
	if not items:
		return default
	# Preserve deterministic order while removing duplicates.
	seen: set[str] = set()
	cleaned: list[str] = []
	for item in items:
		tag = item.strip().strip("[]").upper()
		if not tag or tag in seen:
			continue
		seen.add(tag)
		cleaned.append(tag)
	return tuple(cleaned) or default


@lru_cache(maxsize=1)
def get_runtime_config() -> RuntimeConfig:
	payload: dict = {}
	if LOCAL_CONFIG_PATH.exists():
		try:
			payload = json.loads(LOCAL_CONFIG_PATH.read_text(encoding="utf-8"))
		except json.JSONDecodeError:
			payload = {}

	partner_enabled = _parse_bool(payload.get("partner_enabled"), default=False)
	partner_name = str(payload.get("partner_name") or "Partner").strip() or "Partner"
	school_ranges = _parse_range_list(payload.get("school_holiday_ranges", []))
	kid_free_ranges = _parse_text_line_list(payload.get("partner_kid_free_ranges", []))
	google_calendar_ical_url = str(payload.get("google_calendar_ical_url") or "").strip() or None
	calendar_default_mode = _parse_calendar_default_mode(payload.get("calendar_event_policy_default_mode"))
	calendar_hard_tags = _parse_tag_list(payload.get("calendar_event_policy_hard_tags"), ("BLOCK", "UNAVAILABLE"))
	calendar_together_tags = _parse_tag_list(payload.get("calendar_event_policy_together_tags"), ("TOGETHER",))
	pre_holiday_school_pickup_time = _parse_hhmm_time(payload.get("pre_holiday_school_pickup_time"))
	default_handover_time = _parse_hhmm_time(payload.get("default_handover_time"), default="13:00")
	handover_time_overrides = _parse_handover_time_overrides(payload.get("handover_time_overrides"))
	schedule_visual_default = _parse_schedule_visual_default(payload.get("schedule_visual_default"))
	christmas_split_date = _parse_christmas_split_date(payload.get("christmas_split_date"))
	dad_title = _parse_nonempty_text(payload.get("this_parent") or payload.get("dad_title"), "Dad")
	mum_title = _parse_nonempty_text(payload.get("other_parent") or payload.get("mum_title"), "Mum")
	dad_color = _parse_css_color(payload.get("this_parent_color") or payload.get("dad_color"), "#0f766e")
	mum_color = _parse_css_color(payload.get("other_parent_color") or payload.get("mum_color"), "#b45309")
	partner_available_color = _parse_css_color(payload.get("partner_available_color"), "#22c55e")
	partner_unavailable_color = _parse_css_color(payload.get("partner_unavailable_color"), "#f97316")

	return RuntimeConfig(
		partner_enabled=partner_enabled,
		partner_name=partner_name,
		school_holiday_ranges=school_ranges,
		partner_kid_free_ranges=kid_free_ranges,
		google_calendar_ical_url=google_calendar_ical_url,
		calendar_event_policy_default_mode=calendar_default_mode,
		calendar_event_policy_hard_tags=calendar_hard_tags,
		calendar_event_policy_together_tags=calendar_together_tags,
		pre_holiday_school_pickup_time=pre_holiday_school_pickup_time,
		default_handover_time=default_handover_time,
		handover_time_overrides=handover_time_overrides,
		schedule_visual_default=schedule_visual_default,
		christmas_split_date=christmas_split_date,
		dad_title=dad_title,
		mum_title=mum_title,
		dad_color=dad_color,
		mum_color=mum_color,
		partner_available_color=partner_available_color,
		partner_unavailable_color=partner_unavailable_color,
	)


def get_ui_config() -> dict:
	runtime = get_runtime_config()

	def _serialise(ranges: tuple[ParsedRange, ...]) -> list[dict]:
		return [
			{
				"raw": r.raw,
				"start": r.start.isoformat(),
				"end": r.end.isoformat(),
			}
			for r in ranges
		]

	return {
		"partner_enabled": runtime.partner_enabled,
		"partner_name": runtime.partner_name,
		"school_holiday_ranges": _serialise(runtime.school_holiday_ranges),
		"partner_kid_free_ranges": [{"raw": raw} for raw in runtime.partner_kid_free_ranges],
		"google_calendar_ical_url": runtime.google_calendar_ical_url,
		"calendar_event_policy_default_mode": runtime.calendar_event_policy_default_mode,
		"calendar_event_policy_hard_tags": list(runtime.calendar_event_policy_hard_tags),
		"calendar_event_policy_together_tags": list(runtime.calendar_event_policy_together_tags),
		"pre_holiday_school_pickup_time": runtime.pre_holiday_school_pickup_time,
		"default_handover_time": runtime.default_handover_time,
		"handover_time_overrides": {
			override.day.isoformat(): override.time_text for override in runtime.handover_time_overrides
		},
		"schedule_visual_default": runtime.schedule_visual_default,
		"christmas_split_date": runtime.christmas_split_date,
		"this_parent": runtime.dad_title,
		"other_parent": runtime.mum_title,
		"this_parent_color": runtime.dad_color,
		"other_parent_color": runtime.mum_color,
		"dad_title": runtime.dad_title,
		"mum_title": runtime.mum_title,
		"dad_color": runtime.dad_color,
		"mum_color": runtime.mum_color,
		"partner_available_color": runtime.partner_available_color,
		"partner_unavailable_color": runtime.partner_unavailable_color,
	}
