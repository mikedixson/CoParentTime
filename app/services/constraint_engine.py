from __future__ import annotations

from datetime import datetime

from app.models import CandidatePlan, CoupleTimeWindowOutcome, TimeInterval


def _overlap_seconds(a_start: datetime, a_end: datetime, b_start: datetime, b_end: datetime) -> float:
    start = max(a_start, b_start)
    end = min(a_end, b_end)
    if end <= start:
        return 0.0
    return (end - start).total_seconds()


def _dad_overlaps_exclusion(candidate: CandidatePlan, exclusions: list[TimeInterval]) -> bool:
    dad_blocks = [b for b in candidate.blocks if b.owner == "Dad"]
    for block in dad_blocks:
        for exclusion in exclusions:
            if _overlap_seconds(block.start, block.end, exclusion.start, exclusion.end) > 0:
                return True
    return False


def _couple_overlap_hours(candidate: CandidatePlan, kid_free: list[TimeInterval]) -> float:
    # Couple time exists only while Dad is not parenting (Mum blocks).
    mum_blocks = [b for b in candidate.blocks if b.owner == "Mum"]
    seconds = 0.0
    for block in mum_blocks:
        for interval in kid_free:
            seconds += _overlap_seconds(block.start, block.end, interval.start, interval.end)
    return round(seconds / 3600.0, 2)


def _couple_window_outcomes(
    candidate: CandidatePlan,
    kid_free: list[TimeInterval],
    partner_name: str,
) -> list[CoupleTimeWindowOutcome]:
    mum_blocks = [b for b in candidate.blocks if b.owner == "Mum"]
    outcomes: list[CoupleTimeWindowOutcome] = []

    for interval in kid_free:
        requested_seconds = max(0.0, (interval.end - interval.start).total_seconds())
        covered_seconds = 0.0
        for block in mum_blocks:
            covered_seconds += _overlap_seconds(block.start, block.end, interval.start, interval.end)

        blocked_seconds = max(0.0, requested_seconds - covered_seconds)
        requested_hours = round(requested_seconds / 3600.0, 2)
        covered_hours = round(covered_seconds / 3600.0, 2)
        blocked_hours = round(blocked_seconds / 3600.0, 2)

        if covered_seconds > 0:
            status = "works"
            if blocked_seconds <= 0:
                reason = (
                    f"Fully aligned: Dad can see {partner_name} for {covered_hours}h "
                    f"(blocked for {blocked_hours}h)."
                )
            else:
                reason = (
                    f"Partially aligned: Dad can see {partner_name} for {covered_hours}h "
                    f"(blocked for {blocked_hours}h)."
                )
        else:
            status = "does_not_work"
            reason = (
                f"No overlap: Dad can see {partner_name} for {covered_hours}h "
                f"(blocked for {blocked_hours}h)."
            )

        outcomes.append(
            CoupleTimeWindowOutcome(
                interval_id=interval.id,
                start=interval.start,
                end=interval.end,
                requested_hours=requested_hours,
                covered_hours=covered_hours,
                blocked_hours=blocked_hours,
                status=status,
                reason=reason,
            )
        )

    return outcomes


def validate_candidates(
    candidates: list[CandidatePlan],
    hard_exclusions: list[TimeInterval],
    kid_free: list[TimeInterval],
    partner_name: str = "Partner",
) -> tuple[list[CandidatePlan], list[dict]]:
    audits: list[dict] = []
    valid: list[CandidatePlan] = []

    for candidate in candidates:
        if _dad_overlaps_exclusion(candidate, hard_exclusions):
            candidate.disqualified_reason = "Hard exclusion violated: Dad assigned during exclusion"
            audits.append(
                {
                    "plan_id": candidate.plan_id,
                    "status": "disqualified",
                    "reason": candidate.disqualified_reason,
                }
            )
            continue

        candidate.overlap_hours = _couple_overlap_hours(candidate, kid_free)
        candidate.couple_time_window_outcomes = _couple_window_outcomes(candidate, kid_free, partner_name)
        audits.append(
            {
                "plan_id": candidate.plan_id,
                "status": "valid",
                "reason": "All hard constraints satisfied",
                "overlap_hours": candidate.overlap_hours,
                "couple_time_windows_working": len(
                    [o for o in candidate.couple_time_window_outcomes if o.status == "works"]
                ),
                "couple_time_windows_not_working": len(
                    [o for o in candidate.couple_time_window_outcomes if o.status == "does_not_work"]
                ),
            }
        )
        valid.append(candidate)

    return valid, audits
