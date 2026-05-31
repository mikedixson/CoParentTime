from __future__ import annotations

import json
from pathlib import Path

from app.config import ARTIFACTS_DIR
from app.models import PlanResultPayload


def _candidate_to_table(candidate: dict) -> str:
    rows = ["| Start | End | Owner | Days |", "|---|---|---|---|"]
    for b in candidate.get("blocks", []):
        rows.append(f"| {b['start']} | {b['end']} | {b['owner']} | {b['length_days']} |")
    return "\n".join(rows)


def render_markdown(result: PlanResultPayload) -> str:
    parts = []
    parts.append("# CoParenTime Plan Result")
    parts.append("## Input Summary")
    parts.append("```json\n" + json.dumps(result.input_summary, indent=2) + "\n```")

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
        parts.append(_candidate_to_table(primary))

    if result.couple_time_views:
        works = result.couple_time_views.get("works", [])
        doesnt_work = result.couple_time_views.get("doesnt_work", [])

        parts.append("## Couple Time Works")
        if works:
            for idx, candidate in enumerate(works):
                label = "Primary Couple-Time Option" if idx == 0 else f"Couple-Time Option {idx + 1}"
                parts.append(f"### {label}")
                parts.append(_candidate_to_table(candidate.model_dump(mode="json")))
        else:
            parts.append("No candidate provides couple-time overlap in this window.")

        parts.append("## Couple Time Does Not Work")
        if doesnt_work:
            for idx, candidate in enumerate(doesnt_work):
                parts.append(f"### Non-Working Option {idx + 1}")
                parts.append(_candidate_to_table(candidate.model_dump(mode="json")))
        else:
            parts.append("All top candidates include couple-time overlap.")

    if result.alternatives:
        labels = ["Alternative A", "Alternative B"]
        for idx, alt in enumerate(result.alternatives[:2]):
            parts.append(f"## {labels[idx]}")
            parts.append(_candidate_to_table(alt.model_dump(mode="json")))

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
