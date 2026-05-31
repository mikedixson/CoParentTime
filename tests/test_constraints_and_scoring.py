from __future__ import annotations

from datetime import datetime

from app.config import TIMEZONE
from app.models import CandidatePlan, ParentingBlock, TimeInterval
from app.services.constraint_engine import validate_candidates
from app.services.scoring_engine import score_and_rank


def test_hard_exclusion_disqualifies_dad_assignment():
    candidate = CandidatePlan(
        plan_id="cand-001",
        blocks=[
            ParentingBlock(
                start=datetime(2026, 8, 1, 0, 0, tzinfo=TIMEZONE),
                end=datetime(2026, 8, 8, 0, 0, tzinfo=TIMEZONE),
                length_days=7,
                owner="Dad",
            )
        ],
        fairness_gap_days=0,
        overlap_hours=0,
        transitions=0,
        fragmentation=0,
    )

    exclusion = TimeInterval(
        id="hard-1",
        start=datetime(2026, 8, 2, 0, 0, tzinfo=TIMEZONE),
        end=datetime(2026, 8, 2, 23, 59, tzinfo=TIMEZONE),
        type="hard_exclusion",
        confidence=1.0,
    )

    valid, audit = validate_candidates([candidate], [exclusion], kid_free=[])

    assert valid == []
    assert audit[0]["status"] == "disqualified"


def test_scoring_is_deterministic_for_same_input():
    base = CandidatePlan(
        plan_id="cand-010",
        blocks=[],
        fairness_gap_days=1,
        overlap_hours=4,
        transitions=2,
        fragmentation=1,
    )
    same = CandidatePlan(
        plan_id="cand-011",
        blocks=[],
        fairness_gap_days=1,
        overlap_hours=4,
        transitions=2,
        fragmentation=1,
    )

    ranked_once = score_and_rank([base, same])
    ranked_twice = score_and_rank([base, same])

    assert [c.plan_id for c in ranked_once] == [c.plan_id for c in ranked_twice]
    assert ranked_once[0].score == ranked_twice[0].score


def test_window_outcome_marks_requested_window_not_working_when_dad_has_child():
    candidate = CandidatePlan(
        plan_id="cand-020",
        blocks=[
            ParentingBlock(
                start=datetime(2026, 7, 20, 0, 0, tzinfo=TIMEZONE),
                end=datetime(2026, 7, 27, 0, 0, tzinfo=TIMEZONE),
                length_days=7,
                owner="Dad",
            )
        ],
        fairness_gap_days=0,
        overlap_hours=0,
        transitions=0,
        fragmentation=0,
    )

    requested_window = TimeInterval(
        id="text-1",
        start=datetime(2026, 7, 21, 8, 0, tzinfo=TIMEZONE),
        end=datetime(2026, 7, 22, 9, 0, tzinfo=TIMEZONE),
        type="kid_free",
        confidence=0.95,
    )

    valid, _ = validate_candidates([candidate], hard_exclusions=[], kid_free=[requested_window])
    assert len(valid) == 1

    outcome = valid[0].couple_time_window_outcomes[0]
    assert outcome.status == "does_not_work"
    assert outcome.blocked_hours > 0
    assert "No overlap" in outcome.reason


def test_window_outcome_marks_partial_overlap_as_working():
    candidate = CandidatePlan(
        plan_id="cand-021",
        blocks=[
            ParentingBlock(
                start=datetime(2026, 7, 21, 0, 0, tzinfo=TIMEZONE),
                end=datetime(2026, 7, 22, 0, 0, tzinfo=TIMEZONE),
                length_days=1,
                owner="Dad",
            ),
            ParentingBlock(
                start=datetime(2026, 7, 22, 0, 0, tzinfo=TIMEZONE),
                end=datetime(2026, 7, 23, 0, 0, tzinfo=TIMEZONE),
                length_days=1,
                owner="Mum",
            ),
        ],
        fairness_gap_days=0,
        overlap_hours=0,
        transitions=1,
        fragmentation=0,
    )

    requested_window = TimeInterval(
        id="text-2",
        start=datetime(2026, 7, 21, 12, 0, tzinfo=TIMEZONE),
        end=datetime(2026, 7, 22, 12, 0, tzinfo=TIMEZONE),
        type="kid_free",
        confidence=0.95,
    )

    valid, _ = validate_candidates([candidate], hard_exclusions=[], kid_free=[requested_window])
    assert len(valid) == 1

    outcome = valid[0].couple_time_window_outcomes[0]
    assert outcome.status == "works"
    assert outcome.covered_hours > 0
    assert outcome.blocked_hours > 0
    assert "Partially aligned" in outcome.reason
