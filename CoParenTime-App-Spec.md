# CoParenting Local MVP PoC Spec

## 1. Purpose
Build a locally hosted, lightweight MVP that generates deterministic co-parenting schedules for a selected holiday window, enforces hard constraints, and outputs auditable results.

## 2. Scope (MVP)
In scope:
- Local-only deployment (single machine).
- Deterministic schedule generation using rule hierarchy from role definition.
- Parsing of partner free-text availability into structured intervals.
- Candidate generation (minimum 20 candidates) with 7/14-day block rules.
- Scoring and ranking with explicit audits.
- Exportable results (JSON + human-readable table output).
- Manual holiday date entry in v1.
- Import of hard exclusions via Google Calendar iCal export file in v1.

Out of scope (Phase 2):
- Multi-user auth.
- Cloud hosting.
- Mobile app.
- Real-time collaboration.
- Automated write-back to external calendars.

## 3. Users and Primary Workflow
Primary user: single operator (Dad) running local planning sessions.

Main flow:
1. Select planning period (for example: Summer holidays).
2. Enter holiday window dates manually.
3. Import hard exclusions from Google Calendar iCal export.
4. Input partner kid-free and travel windows (free text).
5. Run parser, interactive clarification when needed, candidate generation, scoring.
6. Review Primary + Alternative A/B outputs with audits.
7. Export plan and audit artifact.

## 4. Functional Requirements
### 4.1 Input Handling
- Accept planning period name and optional explicit date override.
- Accept timezone as Europe/London (fixed in MVP).
- Accept partner free-text windows and classify as kid-free vs exclusion.
- Read iCal (.ics) events exported from Google Calendar as hard exclusions.

### 4.2 Data Retrieval Rules
- v1 uses manual holiday start/end date entry only.
- Optional Phase 2 automation retrieves TCW first, then Tower Hamlets fallback.

### 4.3 Constraint Engine
Implement strict hierarchy:
1. Hard exclusions (absolute).
2. Parenting exclusivity for couple time (absolute): Dad cannot see partner while Dad has the child.
3. Fairness target (50/50, closest feasible when impossible).
4. Block stability (7 or 14-day blocks only).
5. Pre-holiday school pick-up handover rule.
6. Couple-time maximization objective.

Couple-time interpretation for MVP:
- Dad and partner blocks do not need to match exactly.
- A valid couple-time segment is any time overlap where both are child free.
- Full-window coverage is not required; partial overlap counts as successful couple time.

### 4.4 Candidate Generation and Scoring
- Generate at least 20 feasible candidates.
- Disqualify candidates with hard violations.
- Boundary policy defaults to Strict, with optional terminal exception toggle.
- Score remaining candidates with fixed weights:
  - Fairness gap days: 100
  - Couple-time overlap hours: 10
  - Transitions: 2
  - Fragmentation: 1
- Apply deterministic tie-breakers in defined order.

### 4.5 Outputs
Always produce:
- Input Summary.
- Parse Audit Table.
- Primary Schedule Table.
- Alternative A and Alternative B.
- Relationship Optimization Audit.
- Constraint Audit.

Couple-time detail output policy:
- Show per requested kid-free window: status, covered hours, blocked hours, and reason.
- Window status is `works` when covered hours > 0, else `does_not_work`.

## 5. Non-Functional Requirements
- Determinism: identical input yields identical output.
- Performance: target under 10 seconds for a normal holiday run.
- Reliability: robust handling of source outages with explicit blocked state.
- Traceability: full calculation audit persisted per run.
- Privacy: local storage only; no external data sharing beyond configured APIs.

## 6. Proposed Lightweight Architecture
- Frontend: minimal local web UI (optional CLI fallback).
- Backend API: single local service process.
- Core modules:
  - IcalAdapter (Google Calendar iCal import parser).
  - IntervalParser (free-text to normalized intervals).
  - ClarificationEngine (interactive ambiguity resolution).
  - ConstraintValidator.
  - CandidateGenerator.
  - ScoringEngine.
  - ReportRenderer.
- Storage:
  - SQLite for run history and audits.
  - JSON artifacts for exports.

## 7. Data Model (Core)
- TimeInterval: id, start, end, timezone, type, confidence.
- Exclusion: source, reason, interval.
- ParentingBlock: start, end, lengthDays, owner (Dad|Mum).
- CandidatePlan: blocks[], fairnessGapDays, overlapHours, transitions, fragmentation, disqualifiedReason.
- CoupleTimeWindowOutcome: intervalId, start, end, requestedHours, coveredHours, blockedHours, status, reason.
- PlanResult: primary, alternatives[], audits, metadata.

## 8. API Surface (Local)
- POST /plan/run
  - Inputs: planning period, partner text, options.
  - Output: ranked plans + full audit.
- GET /plan/{runId}
  - Output: previously generated result.
- GET /health
  - Output: service status + dependency checks.

## 9. Validation and Error Policy
- If required input missing or ambiguous, return actionable clarification request.
- Never return final schedule when critical ambiguity remains.
- Never assign Dad to hard-exclusion periods.
- Never mark couple time as available during Dad parenting blocks.
- Couple-time success for a requested window is overlap-based: any covered time (>0) is successful, zero covered time is not.

## 10. Testing Strategy
- Unit tests:
  - Parsing normalization and ambiguity detection.
  - iCal import parsing and timezone normalization.
  - Constraint checks and disqualification logic.
  - Deterministic scoring behavior.
- Property tests:
  - No hard exclusion assignments in any valid output.
- Golden tests:
  - Fixed input fixtures produce identical ranked output.
- Integration tests:
  - iCal ingestion and normalization.
  - Interactive clarification flow behavior.

## 11. PoC Milestones
- M1: Local CLI runner with deterministic engine and JSON output.
- M2: Add minimal local web UI, markdown report rendering, and SQLite persistence.
- M3: Add iCal import adapter and interactive clarification flow.
- M4: Hardening: tests, performance pass, and reproducibility checks.

## 12. Confirmed Decisions
1. Stack: Python FastAPI (Option A selected).
2. UI: minimal local web UI.
3. Hard exclusions in v1: Google Calendar iCal import.
4. Holiday dates in v1: manual entry.
5. Runtime target: under 10 seconds.
6. Boundary policy: optional terminal exception.
7. Output formats: JSON + markdown.
8. Persistence: SQLite from day one.
9. Pre-holiday school-day check: manual confirmation.
10. Ambiguity handling: interactive clarification.

## 13. Frozen Build Baseline
- Stack: Python 3.12 + FastAPI + Pydantic + Uvicorn.
- Persistence: SQLite (single local DB file).
- UI: minimal local web UI served by FastAPI templates/static assets.
- Integrations in v1: manual holiday dates + iCal import for hard exclusions.
- Boundary policy: Strict with optional terminal exception toggle.
- Exports: JSON + markdown report.

## 14. Frozen Architecture (MVP)
### 14.1 Runtime Topology
- One local process hosting API, scheduler engine, and web UI.
- One local SQLite database file for run history and audits.
- One local artifacts directory for JSON and markdown exports.

### 14.2 Backend Components
- `api`:
  - HTTP routes for plan execution, run retrieval, health, and clarification flow.
- `app_service`:
  - Orchestrates end-to-end run pipeline and persistence.
- `ical_adapter`:
  - Parses `.ics` input into normalized hard-exclusion intervals.
- `interval_parser`:
  - Parses partner free-text ranges with confidence levels.
- `clarification_engine`:
  - Generates targeted clarification prompts when ambiguity is material.
- `constraint_engine`:
  - Applies hard constraints and disqualification rules.
- `candidate_generator`:
  - Produces at least 20 candidate plans using 7/14-day blocks.
- `scoring_engine`:
  - Deterministic weighted scoring and tie-breaker ranking.
- `report_renderer`:
  - Produces required output sections and markdown summary.

### 14.3 Data and Storage
- SQLite tables:
  - `planning_runs`
  - `run_inputs`
  - `run_candidates`
  - `run_results`
  - `run_audits`
  - `clarification_threads`
- Filesystem artifacts:
  - `artifacts/{run_id}/result.json`
  - `artifacts/{run_id}/report.md`

### 14.4 Determinism and Reliability Controls
- Stable candidate ordering before scoring.
- Fixed timezone normalization to Europe/London.
- Deterministic tie-breaker chain enforced exactly as spec.
- Hard-fail policy for unresolved critical ambiguity.
- Input hash recorded per run for reproducibility checks.

### 14.5 Local Deployment Contract
- Start command: one process (`uvicorn`) listening on localhost only.
- No external write operations in MVP.
- iCal import is file-based only.
- Expected runtime target: under 10 seconds per normal run.

### 14.6 Security and Privacy Baseline
- Localhost bind only (no remote network exposure by default).
- Local data at rest in SQLite and artifacts folder.
- No telemetry required in MVP.

Architecture status: FROZEN for MVP implementation.
