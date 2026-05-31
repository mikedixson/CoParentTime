from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator


IntervalType = Literal["kid_free", "exclusion", "hard_exclusion"]


class TimeInterval(BaseModel):
    id: str
    start: datetime
    end: datetime
    timezone: str = "Europe/London"
    type: IntervalType
    confidence: float = Field(ge=0.0, le=1.0)
    source: str = "user"
    reason: str | None = None


class ParentingBlock(BaseModel):
    start: datetime
    end: datetime
    length_days: int
    owner: Literal["Dad", "Mum"]


class CoupleTimeWindowOutcome(BaseModel):
    interval_id: str
    start: datetime
    end: datetime
    requested_hours: float
    covered_hours: float
    blocked_hours: float
    status: Literal["works", "does_not_work"]
    reason: str


class CandidatePlan(BaseModel):
    plan_id: str
    blocks: list[ParentingBlock]
    fairness_gap_days: float
    overlap_hours: float
    transitions: int
    fragmentation: int
    couple_time_window_outcomes: list[CoupleTimeWindowOutcome] = Field(default_factory=list)
    disqualified_reason: str | None = None
    score: float = 0.0


class ClarificationItem(BaseModel):
    id: str
    prompt: str
    raw_text: str


class ParseResult(BaseModel):
    intervals: list[TimeInterval]
    clarifications: list[ClarificationItem]


class PlanRunRequest(BaseModel):
    planning_period: str = ""
    holiday_start: date
    holiday_end: date
    partner_text: str = ""
    options: dict = Field(default_factory=dict)
    pre_holiday_schoolday_confirmed: bool = False
    ical_content: str | None = None
    ical_file_path: str | None = None
    google_calendar_ical_url: str | None = None
    clarification_responses: dict[str, str] = Field(default_factory=dict)

    @field_validator("holiday_end")
    @classmethod
    def end_after_start(cls, v: date, info):
        start = info.data.get("holiday_start")
        if start and v < start:
            raise ValueError("holiday_end must be on or after holiday_start")
        return v


class PlanResultPayload(BaseModel):
    run_id: str
    status: Literal["ok", "needs_clarification", "blocked"]
    input_summary: dict
    parse_audit: list[dict]
    primary: CandidatePlan | None = None
    alternatives: list[CandidatePlan] = Field(default_factory=list)
    couple_time_views: dict[str, list[CandidatePlan]] = Field(default_factory=dict)
    relationship_optimization_audit: dict = Field(default_factory=dict)
    constraint_audit: list[dict] = Field(default_factory=list)
    clarifications: list[ClarificationItem] = Field(default_factory=list)
    artifacts: dict = Field(default_factory=dict)
    metadata: dict = Field(default_factory=dict)


class PlanRunResponse(BaseModel):
    result: PlanResultPayload


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    checks: dict[str, bool]
