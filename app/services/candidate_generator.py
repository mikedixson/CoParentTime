from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Callable, Literal

from app.config import MIN_CANDIDATES
from app.models import CandidatePlan, ParentingBlock

HandoverResolver = Callable[[date], datetime]


def _build_blocks(
    start: datetime,
    end: datetime,
    handover_at: HandoverResolver,
    first_owner: Literal["Dad", "Mum"],
    block_days: int,
) -> list[ParentingBlock]:
    blocks: list[ParentingBlock] = []
    current = start
    owner = first_owner

    while current < end:
        next_boundary = min(handover_at(current.date() + timedelta(days=block_days)), end)
        days = max(1, (next_boundary.date() - current.date()).days)
        blocks.append(
            ParentingBlock(
                start=current,
                end=next_boundary,
                length_days=days,
                owner=owner,
            )
        )
        owner = "Mum" if owner == "Dad" else "Dad"
        current = next_boundary

    return blocks


def generate_candidates(
    window_start: datetime,
    window_end: datetime,
    handover_at: HandoverResolver,
) -> list[CandidatePlan]:
    total_days = max(1, (window_end.date() - window_start.date()).days)
    candidates: list[CandidatePlan] = []

    shift_offsets = list(range(0, min(10, total_days)))
    block_patterns = [7, 14]
    first_owners: list[Literal["Dad", "Mum"]] = ["Dad", "Mum"]

    idx = 1
    for block_days in block_patterns:
        for first_owner in first_owners:
            for shift in shift_offsets:
                shifted_start = handover_at(window_start.date() + timedelta(days=shift))
                if shifted_start >= window_end:
                    continue

                blocks = []
                if shift > 0:
                    # Deterministic prefix preserves total coverage.
                    blocks.append(
                        ParentingBlock(
                            start=window_start,
                            end=shifted_start,
                            length_days=shift,
                            owner="Dad" if first_owner == "Mum" else "Mum",
                        )
                    )

                blocks.extend(_build_blocks(shifted_start, window_end, handover_at, first_owner, block_days))
                dad_days = sum(b.length_days for b in blocks if b.owner == "Dad")
                mum_days = sum(b.length_days for b in blocks if b.owner == "Mum")
                fairness_gap = abs(dad_days - mum_days)

                transitions = max(0, len(blocks) - 1)
                fragmentation = len([b for b in blocks if b.length_days < block_days])

                candidates.append(
                    CandidatePlan(
                        plan_id=f"cand-{idx:03d}",
                        blocks=blocks,
                        fairness_gap_days=float(fairness_gap),
                        overlap_hours=0.0,
                        transitions=transitions,
                        fragmentation=fragmentation,
                    )
                )
                idx += 1

    # Ensure minimum candidate count via deterministic mirrored variants.
    while len(candidates) < MIN_CANDIDATES:
        seed = candidates[len(candidates) % max(1, len(candidates))]
        mirrored = [
            ParentingBlock(
                start=b.start,
                end=b.end,
                length_days=b.length_days,
                owner="Mum" if b.owner == "Dad" else "Dad",
            )
            for b in seed.blocks
        ]
        dad_days = sum(b.length_days for b in mirrored if b.owner == "Dad")
        mum_days = sum(b.length_days for b in mirrored if b.owner == "Mum")
        candidates.append(
            CandidatePlan(
                plan_id=f"cand-{idx:03d}",
                blocks=mirrored,
                fairness_gap_days=float(abs(dad_days - mum_days)),
                overlap_hours=0.0,
                transitions=max(0, len(mirrored) - 1),
                fragmentation=len([b for b in mirrored if b.length_days < 7]),
            )
        )
        idx += 1

    return candidates
