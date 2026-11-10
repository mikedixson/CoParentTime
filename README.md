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

### VS Code tasks (Windows)
- Use **Tasks: Run Task** -> **CoParenTime: Run App** (or **CoParenTime: Run App (Reload)**) to start the service in a task terminal.
- Use **CoParenTime: Stop App** to stop this workspace's virtual-environment Uvicorn processes and their workers, including instances started outside VS Code tasks. If none are running, the task reports that and exits successfully.
- The stop task uses Windows process inspection; it is not supported on macOS/Linux.

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
   - `christmas_split_date`: optional recurring December/January date in `MM-DD` format (for example `12-26`); absent or `null` keeps standard planning.
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
- Standard planning generates at least 20 deterministic candidates. Configured Christmas splits generate only the two possible parent orders.

## Christmas planning
- Set `christmas_split_date` to a December or January date, for example `"12-26"` or `"01-01"`. January refers to the year after Christmas. Other months, invalid dates, and non-`MM-DD` values are rejected.
- The split uses `default_handover_time`, unless `handover_time_overrides` specifies a time for that exact date. For example, `"christmas_split_date": "12-26"` with `"default_handover_time": "13:00"` hands over at 13:00 on Boxing Day.
- Christmas rules apply automatically to a planning window containing 25 December; preset names do not matter. With a configured split, schedules have exactly two continuous blocks, one parent before the split and the other afterwards.
- The **Christmas Day** toggle uses configured parent names and starts with neither selected. Leave it unselected (or use **Clear selection**) to let existing hard constraints, scoring, and couple-time prioritization choose the parent order while still honouring the configured split.
- Selecting a parent requires that parent to have **all of 25 December**, midnight to midnight in Europe/London. The API accepts optional `christmas_day_parent`: `"this_parent"`, `"other_parent"`, or `null` (default).
- Without a configured split, no selection preserves standard planning. A manual selection filters standard candidates for whole-day ownership instead of introducing a split.
- Active Christmas rules require exactly one whole Christmas Day in the planning window. Partial-day or multiple-Christmas windows are blocked, as are splits outside/at the window boundaries or strictly within Christmas Day. Midnight at the start/end of Christmas Day is allowed if the split remains inside the plan.
- Hard calendar conflicts block the plan rather than changing the split or overriding the selected parent. Blocking reasons are displayed explicitly.
- Non-Christmas plans are unchanged. The UI hides and clears the Christmas choice when dates leave Christmas; an explicit API Christmas selection outside Christmas is rejected with a blocked result.
- Saved results include optional `christmas` context (date, resolved split, requested parent and snapshotted labels). Each candidate records `christmas_day_parent` when a parent covers the whole day. Older saved results remain supported.
- Christmas details appear in reports and shared schedules; timeline/calendar views and iCalendar exports reflect the actual blocks without adding a separate Christmas event. The following-weekend choice remains independent.
- Schedule cards and copied/printed/image schedules use the concise **Christmas Day parent: X. Boxing Day parent: Y** summary, without repeating dates or split times. The overall input summary retains the requested Christmas settings, including split details for blocked or unresolved plans.
- Each Christmas candidate's output shows **Boxing Day parent: X**, using the saved parent label for the last block overlapping Boxing Day in Europe/London (the parent after any Boxing Day handover). Times remain in the blocks. Boxing Day outside the planned window is marked explicitly. This appears in result cards, copied/printed/image schedules, and newly generated Markdown reports.

## Following weekend
- Use the **Following weekend** toggle to select which configured parent will look after the child after the planned period. Neither parent is selected initially; **Clear selection** returns to **Not specified**.
- The displayed weekend is the first **Friday-Sunday** weekend whose Friday is strictly after the plan's end date. A plan ending on Friday refers to the following Friday, not that same day.
- The labels use `this_parent` / `other_parent` from config, including the existing legacy aliases.
- This is informational only: it does not change parenting blocks, candidate ranking, fairness, or calendar events, and does not specify care between the end of the plan and that Friday.
- Run Plan to save the selection; changing the form does not change an already generated result.
- The API accepts optional `following_weekend_parent`: `"this_parent"`, `"other_parent"`, or `null` (default).
- Results include `following_weekend` with `start` (Friday), `end` (Sunday), `parent` (stable side identifier), and `parent_label` (configured name saved at run time). Unselected plans have null parent fields; older results without this context remain supported.
- The note appears in the UI, saved JSON, Markdown report, and copied/printed/image schedules. Calendar exports remain unchanged.
- Copy schedule contains only numbered parenting blocks, followed by the following-weekend note and separate Christmas Day and Boxing Day parent lines when available.

## Test
- Install dev deps:
   - `pip install -r requirements-dev.txt`
- Run:
   - `pytest -q`
