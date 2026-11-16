"""Soft penalties for long hours and low safety."""
from __future__ import annotations

from .config import LONG_HOURS, PENALTY_LONG_HOURS, PENALTY_SAFETY_3, PENALTY_SAFETY_LOW
from .schema import Opportunity


def penalties(opp: Opportunity) -> dict[str, float]:
    hours = PENALTY_LONG_HOURS if opp.hours_per_week > LONG_HOURS else 0.0
    if opp.safety_score == 3:
        safety = PENALTY_SAFETY_3
    elif opp.safety_score <= 2:
        safety = PENALTY_SAFETY_LOW
    else:
        safety = 0.0
    return {"hours": hours, "safety": safety}


def final_score(base: float, pens: dict) -> float:
    return round(max(0.0, base - sum(pens.values())), 3)
