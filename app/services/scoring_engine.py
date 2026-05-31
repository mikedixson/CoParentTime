from __future__ import annotations

from app.models import CandidatePlan

WEIGHTS = {
    "fairness_gap_days": 100,
    "couple_time_overlap_hours": 10,
    "transitions": 2,
    "fragmentation": 1,
}


def score_and_rank(candidates: list[CandidatePlan]) -> list[CandidatePlan]:
    for c in candidates:
        c.score = (
            c.fairness_gap_days * WEIGHTS["fairness_gap_days"]
            - c.overlap_hours * WEIGHTS["couple_time_overlap_hours"]
            + c.transitions * WEIGHTS["transitions"]
            + c.fragmentation * WEIGHTS["fragmentation"]
        )

    ranked = sorted(
        candidates,
        key=lambda c: (
            c.score,
            c.fairness_gap_days,
            -c.overlap_hours,
            c.transitions,
            c.fragmentation,
            c.plan_id,
        ),
    )
    return ranked
