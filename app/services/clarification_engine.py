from app.models import ClarificationItem


def is_critical_ambiguity(clarifications: list[ClarificationItem]) -> bool:
    return len(clarifications) > 0


def build_clarification_payload(clarifications: list[ClarificationItem]) -> list[dict]:
    return [c.model_dump() for c in clarifications]
