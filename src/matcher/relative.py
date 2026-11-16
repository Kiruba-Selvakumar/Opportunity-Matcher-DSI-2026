"""Relative scoring: where a student stands among every eligible student for the same job.

A score of 0.6 means one thing when the student is the strongest of 40 people the job fits, and another when 30 of them
are stronger. Standing is shown as "3rd of 40" and, once at least STANDING_MIN_FIELD students are eligible, nudges the
score by up to STANDING_MAX either way: a student is steered a little toward jobs where they stand out. Jobs only;
training has room for everyone.
"""
from __future__ import annotations

from bisect import bisect_right

from . import adjust, config
from .related import Context
from .schema import MatchRow


def competition(by_student: dict[str, list[MatchRow]]) -> dict[str, list[float]]:
    """listing -> the sorted scores of every eligible student, before standing."""
    out: dict[str, list[float]] = {}
    for rows in by_student.values():
        for r in rows:
            if r.type == "job" and r.eligible:
                out.setdefault(r.opp_id, []).append(adjust.without(r, "standing"))
    return {k: sorted(v) for k, v in out.items()}


def standing(score: float, field: list[float], in_field: bool = True) -> dict:
    """{"rank", "of", "percentile"}: rank 1 is the strongest. Ties share the better rank."""
    above = len(field) - bisect_right(field, score)
    of = len(field) if in_field else len(field) + 1
    rank = above + 1
    return {"rank": rank, "of": of, "percentile": round(1 - (rank - 1) / (of - 1), 3) if of > 1 else 1.0}


def apply(rows: list[MatchRow], ctx: Context, in_field: bool = True) -> list[MatchRow]:
    if not ctx.v3.get("standing") or ctx.competition is None:
        return rows
    out = []
    for r in rows:
        if r.type != "job" or not r.eligible:
            out.append(r.model_copy(update={"standing": None}) if r.standing else r)
            continue
        field = ctx.competition.get(r.opp_id, [])
        st = standing(adjust.without(r, "standing"), field, in_field)
        nudge = config.STANDING_MAX * (st["percentile"] - 0.5) * 2 if st["of"] >= config.STANDING_MIN_FIELD else 0.0
        out.append(adjust.put(r, "standing", nudge, standing=st))
    return out
