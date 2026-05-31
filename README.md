# CoParenTime MVP

Local-only FastAPI MVP for deterministic co-parenting holiday planning with auditable outputs.

## Stack
- Python 3.12
- FastAPI + Pydantic + Uvicorn
- SQLite
- Local templates/static UI

## Run
1. Create and activate a Python environment.
2. Install deps:
   - `pip install -r requirements.txt`
3. Start service:
   - `uvicorn app.main:app --host 127.0.0.1 --port 8000`
4. Open:
   - `http://127.0.0.1:8000`

## API
- `POST /plan/run`
- `GET /plan/{runId}`
- `GET /health`

## Config
- Copy `coparentime.local.example.json` to `coparentime.local.json`.
- `coparentime.local.json` is ignored by git for local-only settings.
- Supported keys:
   - `partner_enabled`: enables partner-availability functionality when `true`; default is `false`.
   - `partner_name`: display name used in UI and couple-time reasoning text.
   - `school_holiday_ranges`: list of date ranges used as holiday presets.
   - `partner_kid_free_ranges`: list of partner availability lines used to prefill partner text (default line means available; `exclude:` / `unavailable:` mark unavailable blocks).
   - `google_calendar_ical_url`: optional Google Calendar iCal feed URL to pull hard exclusions at run time.
   - `pre_holiday_school_pickup_time`: optional school pick-up handover time in `HH:MM` (24h), default `15:30`.
   - `default_handover_time`: optional default handover time in `HH:MM` (24h), default `13:00`.
   - `handover_time_overrides`: optional object mapping handover dates to `HH:MM` overrides. Accepts `yyyyMMdd` or `yyyy-MM-dd` keys.
   - `schedule_visual_default`: default schedule visual mode in UI (`timeline`, `calendar`, or `both`), default `both`.
   - `this_parent` / `other_parent`: optional display labels for the two parenting sides in visual outputs.
   - `dad_title` / `mum_title`: legacy aliases for the same labels (still supported).
   - `this_parent_color` / `other_parent_color`: optional colors for each parenting side in visual outputs.
   - `dad_color` / `mum_color`: legacy aliases for the same parent colors (still supported).
   - `partner_available_color` / `partner_unavailable_color`: optional colors for partner-available vs unavailable blocks.

Google calendar URL notes:
- Paste a direct Google Calendar `.ics` URL.
- For private calendars, use `Settings and sharing -> Integrate calendar -> Secret address in iCal format`.
- `?cid=...` share links do not include private iCal credentials; they are not sufficient for private calendar pulls.
- Keep the secret iCal URL local-only (`coparentime.local.json` is git-ignored) and rotate it in Google Calendar if it is ever exposed.
- If the calendar fetch fails during a plan run, the UI now shows a visible warning banner in the Result panel.
- Supported range formats (start-end):
   - `20/07/2026 - 02/09/2026`
   - `20260720-20260902`
   - `2026-07-20 - 2026-09-02`
   - `summer holidays: 20/07/2026 - 02/09/2026`

Example:

```json
{
   "partner_enabled": true,
   "partner_name": "Alex",
   "school_holiday_ranges": [
      "summer holidays: 20/07/2026 - 02/09/2026"
   ],
   "partner_kid_free_ranges": [
      "2026-07-21 08:00 to 2026-07-22 09:00",
      "exclude: 2026-08-26 to 2026-09-01"
   ],
   "google_calendar_ical_url": "https://calendar.google.com/calendar/ical/your_calendar_id/basic.ics",
   "pre_holiday_school_pickup_time": "15:30",
   "default_handover_time": "13:00",
   "handover_time_overrides": {
      "20260808": "17:00"
   },
   "schedule_visual_default": "both",
   "this_parent": "Parent A",
   "other_parent": "Parent B",
   "this_parent_color": "#0f766e",
   "other_parent_color": "#b45309",
   "partner_available_color": "#22c55e",
   "partner_unavailable_color": "#f97316"
}
```

## Notes
- Timezone is fixed to Europe/London.
- Outputs are written to `artifacts/{run_id}/result.json` and `artifacts/{run_id}/report.md`.
- Minimum 20 deterministic candidate plans are generated.

## Test
- Install dev deps:
   - `pip install -r requirements-dev.txt`
- Run:
   - `pytest -q`
