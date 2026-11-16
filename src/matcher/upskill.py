"""Upskilling preference: between two jobs that fit about as well, prefer the one whose gap is easier to close.

A missing skill is easy to close when the student already knows a related skill (MySQL for SQL), or when an eligible
training or mentor teaches it. Each job's missing skills get an ease from 0 to 1. The weighted ease is the job's reach,
and its potential is the coverage the student could have after a short step: coverage + reach x (1 - coverage).
The nudge is UPSKILL_MAX x (potential - coverage), so it is largest where a lot of fit is within easy reach.
"""
from __future__ import annotations

from . import adjust, config
from .related import Context
from .schema import MatchRow


def ease(related_credit: float, training: dict | None) -> float:
    """How easy one missing skill is to close, from 0 (hard: nothing to build on) to 1 (almost there).

    related_credit: the partial credit the student already earns for this skill from a related one (0 to under 0.5;
        0.2 means only a skill in the same area, higher means a close relative such as MySQL for SQL).
    training: the best eligible training or mentor that teaches it, or None. Keys: "type" ("training" or "mentor"),
        "cost" (rupees up front), "weeks" (how long a batch runs, None if not known), "budget" (the student's, None if not known).
    """
    related = min(1.0, related_credit * 1.8)                # same area 0.2 -> 0.36, a close relative 0.45 -> 0.81
    course = 0.0
    if training:
        course = 0.7 if training["type"] == "training" else 0.5   # a course teaches it; a mentor only guides
        weeks = training["weeks"]
        if weeks:
            course *= 1.0 if weeks <= 4 else 0.85 if weeks <= 8 else 0.7
        if training["cost"]:
            course *= 1 - 0.5 * min(training["cost"] / training["budget"], 1) if training["budget"] else 0.75
    return 1 - (1 - related) * (1 - course)                 # either one helps, and both together help more


def _teachers(rows: list[MatchRow], norm: dict, opps: dict | None) -> dict[str, MatchRow]:
    """For each skill, the best eligible training or mentor that teaches it."""
    best: dict[str, MatchRow] = {}
    for r in rows:
        if r.type not in ("training", "mentor") or not r.eligible:
            continue
        for s in norm["opportunities"][r.opp_id]["skills"]:
            cur = best.get(s)
            if cur is None or (r.upfront_cost, -r.final_score) < (cur.upfront_cost, -cur.final_score):
                best[s] = r
    return best


def apply(rows: list[MatchRow], norm: dict, ctx: Context, skills: list[str], budget: int | None = None,
          opps: dict | None = None) -> list[MatchRow]:
    """Add the upskill nudge and its explanation to every job with missing skills."""
    if not ctx.v3.get("upskill"):
        return rows
    teachers = _teachers(rows, norm, opps)
    nice_of = {oid: set(n.get("nice", [])) for oid, n in norm["opportunities"].items()}
    out = []
    for r in rows:
        if r.type != "job" or not r.missing:
            out.append(r)
            continue
        total = got = 0.0
        steps = []
        for m in r.missing:
            w = ctx.weight(m, m in nice_of.get(r.opp_id, set()))
            credit, who = ctx.credit(skills, m)
            t = teachers.get(m)
            # a course's length makes a gap harder to close; a mentor's is time with a guide, so it is not counted
            weeks = (opps or {}).get(t.opp_id).duration_weeks if t and t.type == "training" and opps and t.opp_id in opps else None
            e = max(0.0, min(1.0, ease(credit, {"type": t.type, "cost": t.upfront_cost, "weeks": weeks, "budget": budget} if t else None)))
            total += w
            got += w * e
            steps.append({"skill": m, "ease": round(e, 2), "from": who if credit > 0 else None,
                          "via": {"opp_id": t.opp_id, "title": t.title, "type": t.type, "cost": t.upfront_cost} if t else None})
        reach = got / total if total else 0.0
        potential = r.coverage + reach * (1 - r.coverage)
        nudge = config.UPSKILL_MAX * (potential - r.coverage)
        out.append(adjust.put(r, "upskill", nudge, upskill={"reach": round(reach, 3), "potential": round(potential, 3), "steps": steps}))
    return out
