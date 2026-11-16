"""Add or replace one named nudge on a match and recompute its final score the same way score.py does."""
from __future__ import annotations

from . import config
from .schema import MatchRow


def total(r: MatchRow, adjustments: dict[str, float]) -> float:
    final = round(min(1.0, max(0.0, r.base_score + sum(adjustments.values()) - r.penalty_hours - r.penalty_safety)), 3)
    if r.type == "training" and config.V2.get("training") and not r.teaches:      # training.finalize: nothing to learn, never shown
        final = min(final, round(config.MIN_SHOW_SCORE / 2, 3))
    return final


def put(r: MatchRow, name: str, value: float, **fields) -> MatchRow:
    """A copy of r with adjustments[name] = value (dropped when 0) and any extra fields set."""
    adj = {k: v for k, v in r.adjustments.items() if k != name}
    if round(value, 4):
        adj[name] = round(value, 4)
    return r.model_copy(update={"adjustments": adj, "final_score": total(r, adj), **fields})


def without(r: MatchRow, name: str) -> float:
    """The final score r would have without one nudge."""
    return total(r, {k: v for k, v in r.adjustments.items() if k != name})
