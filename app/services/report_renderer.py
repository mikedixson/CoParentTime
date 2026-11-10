from __future__ import annotations

import json
from datetime import datetime, time, timedelta
from pathlib import Path

from app.config import ARTIFACTS_DIR, TIMEZONE
from app.models import ChristmasContext, PlanResultPayload


def _boxing_day_text(candidate: dict, christmas: ChristmasContext) -> str:
    if not christmas.christmas_day:
        return ""
    day = christmas.christmas_day + timedelta(days=1)
    day_start = datetime.combine(day, time.min, tzinfo=TIMEZONE)
    day_end = day_start + timedelta(days=1)
    for block in sorted(candidate.get("blocks", []), key=lambda block: block["start"], reverse=True):
        start = max(datetime.fromisoformat(block["start"]).astimezone(TIMEZONE), day_start)
        end = min(datetime.fromisoformat(block["end"]).astimezone(TIMEZONE), day_end)
        if start >= end:
            continue
        parent = "this_parent" if block["owner"] == "Dad" else "other_parent"
        return f"Boxing Day parent: {christmas.parent_labels[parent]}"
    return "Boxing Day parent: Outside planned window"


def _candidate_to_table(candidate: dict, christmas: ChristmasContext | None = None) -> str:
    rows = ["| Start | End | Owner | Days |", "|---|---|---|---|"]
    for b in candidate.get("blocks", []):
        rows.append(f"| {b['start']} | {b['end']} | {b['owner']} | {b['length_days']} |")
    if christmas:
        parent = candidate.get("christmas_day_parent")
        label = christmas.parent_labels[parent] if parent else "No whole-day assignment"
        rows.extend(["", f"Christmas Day parent: {label}."])
        boxing_day = _boxing_day_text(candidate, christmas)
        if boxing_day:
            rows.extend(["", boxing_day])
    return "\n".join(rows)


def render_markdown(result: PlanResultPayload) -> str:
    parts = []
    parts.append("# CoParenTime Plan Result")
    parts.append("## Input Summary")
    parts.append("```json\n" + json.dumps(result.input_summary, indent=2) + "\n```")

    if result.christmas:
        christmas = result.christmas
        parts.append("## Christmas Planning")
        parts.append(f"Christmas Day: {christmas.christmas_day or 'Not resolved'}.")
        parts.append(f"Requested parent: {christmas.requested_parent_label or 'Automatic (planner chooses)'}.")
        parts.append(
            f"Split: {christmas.split_at.isoformat()} (Europe/London)."
            if christmas.split_at else (
                "Christmas split could not be resolved."
                if christmas.mode == "configured_split" else "Standard planning; no Christmas split configured."
            )
        )
        if result.status == "blocked":
            parts.append(f"Blocked: {result.metadata.get('reason', 'No feasible Christmas schedule')}")

    if result.following_weekend:
        weekend = result.following_weekend
        parts.append("## Following Weekend (Informational Only)")
        parts.append(
            f"Friday {weekend.start.isoformat()} to Sunday {weekend.end.isoformat()}: "
            f"{weekend.parent_label if weekend.parent is not None else 'Not specified'}.\n\n"
            "This note does not change the planned schedule or specify care before that Friday."
        )

    parts.append("## Parse Audit Table")
    parts.append("| Interval ID | Type | Start | End | Confidence |")
    parts.append("|---|---|---|---|---|")
    for row in result.parse_audit:
        parts.append(
            f"| {row.get('id','')} | {row.get('type','')} | {row.get('start','')} | {row.get('end','')} | {row.get('confidence','')} |"
        )

    if result.primary:
        primary = result.primary.model_dump(mode="json")
        parts.append("## Primary Schedule Table")
        parts.append(_candidate_to_table(primary, result.christmas))

    if result.couple_time_views:
        works = result.couple_time_views.get("works", [])
        doesnt_work = result.couple_time_views.get("doesnt_work", [])

        parts.append("## Couple Time Works")
        if works:
            for idx, candidate in enumerate(works):
                label = "Primary Couple-Time Option" if idx == 0 else f"Couple-Time Option {idx + 1}"
                parts.append(f"### {label}")
                parts.append(_candidate_to_table(candidate.model_dump(mode="json"), result.christmas))
        else:
            parts.append("No candidate provides couple-time overlap in this window.")

        parts.append("## Couple Time Does Not Work")
        if doesnt_work:
            for idx, candidate in enumerate(doesnt_work):
                parts.append(f"### Non-Working Option {idx + 1}")
                parts.append(_candidate_to_table(candidate.model_dump(mode="json"), result.christmas))
        else:
            parts.append("All top candidates include couple-time overlap.")

    if result.alternatives:
        labels = ["Alternative A", "Alternative B"]
        for idx, alt in enumerate(result.alternatives[:2]):
            parts.append(f"## {labels[idx]}")
            parts.append(_candidate_to_table(alt.model_dump(mode="json"), result.christmas))

    parts.append("## Relationship Optimization Audit")
    parts.append("```json\n" + json.dumps(result.relationship_optimization_audit, indent=2) + "\n```")

    parts.append("## Constraint Audit")
    parts.append("```json\n" + json.dumps(result.constraint_audit, indent=2) + "\n```")

    return "\n\n".join(parts) + "\n"


def write_artifacts(result: PlanResultPayload) -> dict:
    run_dir = ARTIFACTS_DIR / result.run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    json_path = run_dir / "result.json"
    md_path = run_dir / "report.md"

    json_path.write_text(result.model_dump_json(indent=2), encoding="utf-8")
    md_path.write_text(render_markdown(result), encoding="utf-8")

    return {
        "json": str(json_path),
        "markdown": str(md_path),
    }
