# CoParentTime

> **Deterministic co-parenting holiday schedules with transparency and fairness**

Generate optimized parenting schedules for school holidays with built-in conflict resolution, couple-time maximization, and complete audit trails.

![Python 3.12+](https://img.shields.io/badge/Python-3.12%2B-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-Latest-green)
![Local-Only](https://img.shields.io/badge/Deployment-Local--Only-purple)

## 🎯 The Problem

Co-parenting holiday scheduling involves competing priorities:
- **Fairness**: Both parents get equal time, but schedules are complex
- **Flexibility**: Partner availability windows are real-world constraints
- **Logistics**: School pickup times, handover points, and continuity matter
- **Trust**: How do you compare different schedule options objectively?

Manually juggling these factors leads to friction, incomplete optimization, and repeated negotiations.

## ✨ What CoParentTime Solves

CoParentTime generates **deterministic, auditable parenting schedules** that optimize multiple factors simultaneously:

1. **Fairness & Accuracy**: Calculates time splits down to the hour with transparent fairness gaps
2. **Couple Time**: Maximizes overlap between both parents' kid-free windows
3. **Stability**: Prefers multi-day blocks (7 or 14 days) over fragmented splits
4. **Hard Constraints**: Respects exclusions from calendars, hard commitments, and manual input
5. **Complete Transparency**: Every decision is auditable with full scoring breakdown
6. **Multiple Options**: Generates 20+ ranked candidate plans so you can explore tradeoffs

All runs are reproducible, local-only, and privacy-respecting.

## 🚀 Key Features

### Schedule Optimization
- **Deterministic ranking** of candidate schedules with explicit tie-breakers
- **Configurable fairness targets**: Default 50/50 split, or customize to e.g. 70/30
- **Weighted optimization**: Tune between couple-time and fairness priorities
- **Couple-time analysis**: See exactly where both parents are kid-free simultaneously
- **Conflict explanation**: Understand why no feasible plan exists if constraints are over-constrained

### Calendar & Availability
- **Google Calendar integration**: Import hard exclusions via private iCal feed
- **Partner availability parsing**: Enter free-text time windows (e.g., "2026-07-21 08:00 to 2026-07-22 09:00")
- **Flexible exclusion format**: Text ranges, dates, or calendar feeds
- **School holiday presets**: Save and reuse recurring holiday windows (summer, half-terms, etc.)

### Outputs & Export
- **Visual schedule**: View plans as timeline or calendar view with customizable colors
- **Comprehensive reports**: JSON artifacts with full audit trails
- **What-if comparison**: Compare two schedule options with side-by-side metrics
- **Image export**: Copy result cards as PNG (full or couple-info redacted)
- **iCalendar export**: Export finalized schedule as .ics files for each parent

### Configuration & Customization
- **Local config file**: All settings stored locally in `coparentime.local.json` (git-ignored for secrets)
- **Parent labels**: Customize names for "this_parent" and "other_parent" (or legacy "dad" / "mum")
- **Visual theming**: Choose colors for timeline displays and partner availability indicators
- **Handover timing**: Set school pickup times and default handover times
- **Timezone fixed to Europe/London** for deterministic behavior

## 👥 Who is This For?

- **Divorced/separated co-parents** planning holidays fairly and transparently
- **Co-parenting partnerships** with complex schedules or partner availability constraints
- **Relationship mediators** who need objective, auditable schedule options
- **Family organizations** with privacy concerns about cloud-based planning tools

## ⚡ Quick Start

### Installation

```bash
# 1. Clone the repository
git clone https://github.com/mikedixson/CoParentTime.git
cd CoParentTime

# 2. Create and activate a Python environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt
```

### Running the Application

```bash
# Start the local server
uvicorn app.main:app --host 127.0.0.1 --port 8000

# Open in your browser
open http://127.0.0.1:8000
```

The app is now accessible at `http://127.0.0.1:8000` in your browser.

## 🔧 Configuration

### Setup

1. Copy the example config:
   ```bash
   cp coparentime.local.example.json coparentime.local.json
   ```

2. Edit `coparentime.local.json` with your details (this file is git-ignored for privacy)

### Core Settings

| Setting | Purpose | Example |
|---------|---------|---------|
| `partner_enabled` | Enable partner availability mode | `true` / `false` |
| `partner_name` | Display name for the co-parent | `"Alex"` |
| `school_holiday_ranges` | Recurring holiday windows to preset | `["summer holidays: 20/07/2026 - 02/09/2026"]` |
| `this_parent` / `other_parent` | Custom labels for each parent | `"Parent A"` / `"Parent B"` |

### Calendar Integration

| Setting | Purpose | Notes |
|---------|---------|-------|
| `google_calendar_ical_url` | Private Google Calendar iCal feed | Use secret iCal URL (not share link) |
| `partner_kid_free_ranges` | Free-text availability windows | Supports "exclude:" prefix for unavailable blocks |
| `pre_holiday_school_pickup_time` | School pickup time (24h format) | Default: `"15:30"` |
| `default_handover_time` | Default handover time (24h format) | Default: `"13:00"` |
| `handover_time_overrides` | Date-specific handover times | `{"20260808": "17:00"}` |

### Visual Display

| Setting | Purpose | Options |
|---------|---------|---------|
| `schedule_visual_default` | Default schedule view | `"timeline"` / `"calendar"` / `"both"` |
| `this_parent_color` / `other_parent_color` | Parent colors in visuals | CSS hex colors e.g., `"#0f766e"` |
| `partner_available_color` / `partner_unavailable_color` | Partner availability colors | CSS hex colors e.g., `"#22c55e"` / `"#f97316"` |

### Full Configuration Example

```json
{
   "partner_enabled": true,
   "partner_name": "Alex",
   "school_holiday_ranges": [
      "summer holidays: 20/07/2026 - 02/09/2026",
      "easter holidays: 05/04/2026 - 19/04/2026"
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

### Google Calendar Integration Details

To use Google Calendar with CoParentTime:

1. Open your Google Calendar
2. Go to **Settings and sharing → Integrate calendar → Secret address in iCal format**
3. Copy the secret iCal URL (not a public share link)
4. Paste into `google_calendar_ical_url` in `coparentime.local.json`

**⚠️ Security Note**: Keep the secret iCal URL local-only. The `.json` file is git-ignored. If exposed, regenerate the URL in Google Calendar settings.

### Supported Date Formats

The app accepts multiple date range formats:

- `20/07/2026 - 02/09/2026` (DD/MM/YYYY)
- `20260720-20260902` (YYYYMMDD)
- `2026-07-20 - 2026-09-02` (YYYY-MM-DD)
- `summer holidays: 20/07/2026 - 02/09/2026` (with label)

## 🔌 API Reference

The application provides a RESTful API for programmatic access:

### Endpoints

- **`POST /plan/run`** - Generate new parenting schedule
  - Accepts: holiday dates, partner availability, configuration overrides
  - Returns: ranked candidate plans with full audit trails
  
- **`GET /plan/{runId}`** - Retrieve previously generated plan
  - Returns: stored plan result and all audit data
  
- **`GET /health`** - Check service health
  - Returns: service status and dependency information

All responses include complete audit trails for reproducibility.

## 📊 How It Works

1. **Input Phase**: Enter holiday dates, partner availability, constraints
2. **Parsing**: Free-text windows converted to structured time intervals
3. **Calendar Import**: Google Calendar exclusions fetched (if configured)
4. **Candidate Generation**: 20+ feasible schedules generated using block rules
5. **Scoring**: Candidates ranked by fairness, couple-time, stability, transitions
6. **Output**: Primary + 2 alternative options with complete breakdown

The algorithm is **deterministic**: identical inputs always produce identical outputs, making runs fully reproducible.

## 🔒 Privacy & Security

- **Local-only deployment**: No cloud services, data stays on your machine
- **Git-ignored secrets**: Calendar URLs and configs stored locally in `.json` (ignored by git)
- **No telemetry**: No external data sharing
- **Transparent computation**: All scoring and decisions are auditable
- **Security headers**: Web UI protected with standard HTTP security headers

## 🧪 Testing

### Run Tests

```bash
# Install dev dependencies
pip install -r requirements-dev.txt

# Run test suite
pytest -q
```

### Test Coverage

- Unit tests for parsing, constraints, and scoring logic
- Integration tests for calendar import and full runs
- Golden tests ensuring deterministic output consistency
- Security tests for path validation and SSRF prevention

## 📈 Roadmap & Future Development

CoParentTime is actively developed. See [FEATURE_ROADMAP.md](FEATURE_ROADMAP.md) for the complete feature roadmap.

### Currently Implemented
- ✅ Core scheduling engine with deterministic optimization
- ✅ Google Calendar integration (iCal import)
- ✅ Partner availability parsing (free-text and structured input)
- ✅ Custom fairness weighting (tune couple-time vs. fairness balance)
- ✅ What-if comparison (compare two schedule options)
- ✅ Image export (copy result cards as PNG)
- ✅ iCalendar export (.ics files for each parent)
- ✅ Custom split targets (configurable fairness targets like 70/30)
- ✅ School holiday presets (save and reuse holiday windows)
- ✅ Hard-constraint conflict detection (explain infeasible constraints)

### Planned Features
- 🔄 Lock specific dates to a parent before optimization (manual override pins)
- 🔄 Enhanced UI features and preset management
- 🔄 Additional calendar export formats

## 📝 Architecture

CoParentTime uses:
- **Backend**: Python 3.12 + FastAPI + Pydantic
- **Database**: SQLite (local file-based)
- **Frontend**: Local HTML/CSS/JavaScript UI
- **Scheduler**: Deterministic candidate generator with weighted scoring

All data stays local. No external services required beyond optional Google Calendar integration.

## 💡 Use Cases

### Individual Co-Parents
Use for quarterly or semester holiday planning to reduce negotiation friction.

### Mediators
Generate objective schedule options to present to both parties with transparent scoring.

### Shared Custody Organizations
Batch process multiple families with consistent, auditable outputs.

## 📄 Output Artifacts

Each planning run generates:

- **`result.json`**: Complete schedule with all metrics and audit data
- **`report.md`**: Human-readable summary with tables and scoring breakdown
- **`run_metadata`**: Input snapshot for reproducibility checks

All artifacts are stored in `artifacts/{run_id}/` with full audit trails.

## ❓ Troubleshooting

### Calendar fetch failed warning
If you see a warning about calendar import failure:
1. Verify your `google_calendar_ical_url` is correct
2. Check that it's the secret iCal URL, not a public share link
3. Ensure your internet connection is working
4. Schedules will still be generated using manual constraints if calendar fetch fails

### "No feasible plan" error
If the algorithm reports no feasible plans:
1. Check constraint conflicts in the detailed error message
2. Consider relaxing hard constraints (e.g., removing impossible date restrictions)
3. Verify partner availability windows don't conflict with holiday dates
4. Review the constraint audit in the output for details

### Parsing ambiguity
If you enter partner availability with ambiguous phrasing:
1. Use explicit date formats: `2026-07-21 to 2026-07-22`
2. Include times when relevant: `2026-07-21 09:00 to 2026-07-22 17:00`
3. Use `exclude:` prefix for unavailable blocks: `exclude: 2026-08-26 to 2026-09-01`

## 🤝 Contributing

Contributions are welcome! See [FEATURE_ROADMAP.md](FEATURE_ROADMAP.md) for planned features and implementation guidance.

To contribute:
1. Fork the repository
2. Create a feature branch
3. Make your changes with tests
4. Submit a pull request

## 📚 Documentation

- **[FEATURE_ROADMAP.md](FEATURE_ROADMAP.md)** - Upcoming features and implementation priorities
- **[CoParenTime-App-Spec.md](CoParenTime-App-Spec.md)** - Complete application specification
- **[SECURITY_AUDIT.md](SECURITY_AUDIT.md)** - Security considerations and audit details

## 📄 License

This project is licensed under the MIT License. See LICENSE file for details.

## 🎓 How Scoring Works

CoParentTime uses a multi-factor scoring system:

1. **Fairness Gap** (weight: 100): Days difference from target split (50/50 or custom)
2. **Couple-Time Hours** (weight: 10): Overlap hours when both parents are kid-free
3. **Transitions** (weight: 2): Number of parent transitions
4. **Fragmentation** (weight: 1): Number of separate blocks

Candidates are ranked by total score, with deterministic tie-breakers for reproducibility.

## 🌍 Localization

Currently optimized for:
- **Timezone**: Europe/London (fixed)
- **Date formats**: DD/MM/YYYY, YYYY-MM-DD, YYYYMMDD
- **School systems**: UK school holidays (configurable presets)

Future versions may support additional timezones and regions.

## 💬 Getting Help

- Check the configuration examples in this README
- Review the [CoParenTime-App-Spec.md](CoParenTime-App-Spec.md) for detailed behavior
- Examine output audit trails - they explain every decision
- Open an issue on GitHub with your scenario

---

**Made with ❤️ for co-parents everywhere**
