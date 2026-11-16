"""Training is valuable for what it teaches, not for what the student already knows.

A student's skill gap is the set of skills that their best job matches ask for and they lack. A training listing is
scored by how much of that gap it closes. With no eligible job there is no gap, and training scores low rather than
filling the list.
"""
from __future__ import annotations

from . import config
from .related import Context
from .schema import MatchRow


def finalize(rows: list[MatchRow], norm: dict, ctx: Context) -> list[MatchRow]:
    """Re-score the training rows of one student, after every job row has a score."""
    if not ctx.flags.get("training"):
        return rows
    jobs = sorted((r for r in rows if r.type == "job" and r.eligible), key=lambda r: -r.final_score)[:config.TRAIN_JOBS]
    gap: dict[str, float] = {}
    for r in jobs:
        for s in r.missing:
            gap[s] = gap.get(s, 0.0) + ctx.weight(s, False)
    total = sum(gap.values())
    out = []
    for r in rows:
        if r.type != "training":
            out.append(r)
            continue
        teaches = [s for s in norm["opportunities"][r.opp_id]["skills"] if s in gap]
        value = sum(gap[s] for s in teaches) / total if total else 0.0
        base = round(config.TRAIN_W_SIM * r.skill_sim + config.TRAIN_W_GAP * value, 4)
        final = round(min(1.0, max(0.0, base + sum(r.adjustments.values()) - r.penalty_hours - r.penalty_safety)), 3)
        if not teaches:                                      # nothing to learn from it: never recommend it
            final = min(final, round(config.MIN_SHOW_SCORE / 2, 3))
        out.append(r.model_copy(update={"coverage": round(value, 3), "base_score": base, "final_score": final, "teaches": teaches}))
    return out
