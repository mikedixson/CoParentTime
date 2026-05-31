from __future__ import annotations

from app.models import PlanRunRequest
from app.services.app_service import run_planning


def _request() -> PlanRunRequest:
    return PlanRunRequest(
        planning_period="Summer",
        holiday_start="2026-08-01",
        holiday_end="2026-08-21",
        partner_text="kidfree: 2026-08-03 18:00 to 2026-08-05 18:00\nexclude: 2026-08-10 to 2026-08-11",
        pre_holiday_schoolday_confirmed=True,
        options={"boundary_policy": "Strict", "terminal_exception": False},
    )


def test_golden_ranked_output_is_stable():
    first = run_planning(_request())
    second = run_planning(_request())

    assert first.status == "ok"
    assert second.status == "ok"

    assert first.primary is not None
    assert second.primary is not None

    assert first.primary.plan_id == second.primary.plan_id
    assert first.primary.fairness_gap_days == second.primary.fairness_gap_days
    assert first.primary.overlap_hours == second.primary.overlap_hours

    assert [a.plan_id for a in first.alternatives] == [a.plan_id for a in second.alternatives]

    assert set(first.couple_time_views.keys()) == {"works", "doesnt_work"}
    assert set(second.couple_time_views.keys()) == {"works", "doesnt_work"}

    if first.couple_time_views["works"]:
        assert first.primary.overlap_hours > 0
    if second.couple_time_views["works"]:
        assert second.primary.overlap_hours > 0
