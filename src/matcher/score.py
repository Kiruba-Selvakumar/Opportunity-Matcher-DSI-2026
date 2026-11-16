"""Skill scores and the full pair table."""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

from . import config
from .config import PATHS, WEIGHT_COVERAGE, WEIGHT_SIM
from .embed import get_encoder, profile_vector
from .filters import check_all, is_eligible
from .penalties import penalties
from .related import STATE, Context, congestion_penalty, prior_adjustment
from .skills import technical
from .training import finalize
from .schema import MatchRow, Opportunity, Student


def skill_scores(student_vecs: np.ndarray, opp_vecs: np.ndarray) -> np.ndarray:
    """Cosine similarity for every pair, clipped to [0, 1]. Vectors are already L2-normalized."""
    return np.clip(np.asarray(student_vecs) @ np.asarray(opp_vecs).T, 0.0, 1.0)


def coverage(student_skills: list[str], required: list[str]) -> tuple[float, list[str], list[str]]:
    if not required:
        return 1.0, [], []
    have = set(student_skills)
    overlap = [s for s in required if s in have]
    missing = [s for s in required if s not in have]
    return round(len(overlap) / len(required), 3), overlap, missing


def base_score(sim: float, cov: float) -> float:
    return round(WEIGHT_SIM * sim + WEIGHT_COVERAGE * cov, 4)


def weighted_coverage(have: list[str], required: list[str], nice: list[str], ctx: Context) -> tuple[float, list[str], list[str], list[dict]]:
    """Share of the needed skills the student covers, with rare skills counting more and related skills counting partly.

    Returns (coverage, exact matches, missing, partial credits). A skill is missing when nothing the student has
    gets at least half credit for it.
    """
    if not required:
        return 1.0, [], [], []
    nice_set = set(nice)
    total = got = 0.0
    overlap: list[str] = []
    missing: list[str] = []
    partial: list[dict] = []
    for r in required:
        w = ctx.weight(r, r in nice_set)
        c, who = ctx.credit(have, r)
        total += w
        got += w * c
        if c >= 1.0:
            overlap.append(r)
        else:
            if c > 0 and who:
                partial.append({"have": who, "need": r, "credit": round(c, 2)})
            if c < 0.5:
                missing.append(r)
    return round(got / total, 3), overlap, missing, partial


def soft_terms(student: Student, opp: Opportunity, checks: dict, ctx: Context) -> dict[str, float]:
    """Small, capped nudges. They never decide a match on their own, and every one is shown to staff."""
    if not ctx.flags.get("soft"):
        return {}
    out: dict[str, float] = {}
    fit = ctx.branch_fit.get((student.branch, opp.job_family))
    if fit:
        out["branch_fit"] = fit
    moves = opp.mode != "remote" and opp.city != student.college_town
    if moves and student.can_relocate and STATE.get(opp.city) and STATE.get(opp.city) == STATE.get(student.college_town):
        out["home_state"] = config.HOME_STATE_BONUS
    if opp.type == "job" and student.cgpa is not None and student.cgpa < config.LOW_CGPA:
        out["low_cgpa"] = -config.LOW_CGPA_PENALTY
    return out


def opp_vectors(opps: list[Opportunity], norm: dict, enc, tech: bool = True) -> dict[str, np.ndarray]:
    """One profile vector per listing. By default soft skills and certificates are left out (see skills.technical)."""
    pick = technical if tech else (lambda s: s)
    return {o.opp_id: profile_vector(pick(norm["opportunities"][o.opp_id]["skills"]), enc) for o in opps}


def student_vector(skills: list[str], enc, ctx: Context) -> np.ndarray:
    return profile_vector(technical(skills) if ctx.flags.get("tech_sim") else skills, enc)


def score_pair(student: Student, o: Opportunity, s_skills: list[str], s_vec: np.ndarray, norm: dict,
               o_vec: np.ndarray, ctx: Context) -> MatchRow:
    """One student against one listing."""
    n = norm["opportunities"][o.opp_id]
    sim = float(np.clip(s_vec @ o_vec, 0.0, 1.0))
    cov, overlap, missing, partial = weighted_coverage(s_skills, n["skills"], n.get("nice", []), ctx)
    base = base_score(sim, cov)
    checks = check_all(student, o)
    pens = penalties(o)
    adj = soft_terms(student, o, checks, ctx)
    crowd = congestion_penalty(ctx, o)
    if crowd:
        adj["crowded"] = -crowd
    pri, pri_note = prior_adjustment(ctx, o.job_family)
    if pri:
        adj["staff_prior"] = pri
    final = round(min(1.0, max(0.0, base + sum(adj.values()) - sum(pens.values()))), 3)
    return MatchRow(
        student_id=student.student_id, opp_id=o.opp_id, type=o.type, title=o.title, org_name=o.org_name,
        city=o.city, mode=o.mode, pay_min=o.pay_min, pay_max=o.pay_max, upfront_cost=o.upfront_cost,
        skill_sim=round(sim, 4), coverage=cov, overlap=overlap, missing=missing, base_score=base,
        checks=checks, penalty_hours=pens["hours"], penalty_safety=pens["safety"],
        final_score=final, eligible=is_eligible(checks), related=partial,
        adjustments={k: round(v, 4) for k, v in adj.items() if v}, crowded=bool(crowd),
        prior_note=pri_note if pri else None, nice_missing=[m for m in missing if m in n.get("nice", [])])


def finish(rows: list[MatchRow], norm: dict, ctx: Context, student: Student, skills: list[str],
           opps: dict[str, Opportunity] | None = None, in_field: bool = True) -> list[MatchRow]:
    """The terms that need all of one student's rows, in order: training by the gap it closes, upskilling, the learned
    nudge (once ctx.model is trained) and standing among other students (once ctx.competition is known)."""
    from . import learn, relative, upskill
    rows = finalize(rows, norm, ctx)
    rows = upskill.apply(rows, norm, ctx, skills, student.budget, opps)
    rows = learn.apply(rows, ctx)
    return relative.apply(rows, ctx, in_field)


def score_student(student: Student, opps: list[Opportunity], norm: dict, enc,
                  opp_vecs: dict[str, np.ndarray] | None = None, ctx: Context | None = None, in_field: bool = True) -> list[MatchRow]:
    """Score one student against every opportunity. No file reads or writes (the what-if panel uses it)."""
    opp_vecs = opp_vecs or opp_vectors(opps, norm, enc)
    ctx = ctx or Context.build(opps, norm)
    s_skills = norm["students"][student.student_id]["skills"]
    s_vec = student_vector(s_skills, enc, ctx)
    rows = [score_pair(student, o, s_skills, s_vec, norm, opp_vecs[o.opp_id], ctx) for o in opps]
    return finish(rows, norm, ctx, student, s_skills, {o.opp_id: o for o in opps}, in_field)


def load_clean() -> tuple[list[Student], list[Opportunity], dict]:
    students = [Student(**d) for d in json.loads(PATHS["students"].read_text())]
    opps = [Opportunity(**d) for d in json.loads(PATHS["opportunities"].read_text())]
    norm = json.loads(PATHS["normalized"].read_text())
    return students, opps, norm


def rows_to_frame(rows: list[MatchRow]) -> pd.DataFrame:
    recs = []
    for r in rows:
        c = r.checks
        recs.append({
            "student_id": r.student_id, "opp_id": r.opp_id, "skill_sim": r.skill_sim, "coverage": r.coverage,
            "overlap": "|".join(r.overlap), "missing": "|".join(r.missing), "base_score": r.base_score,
            "location": c["location"].status, "location_note": c["location"].note,
            "budget": c["budget"].status, "budget_note": c["budget"].note,
            "language": c["language"].status, "language_note": c["language"].note,
            "family": c["family"].status, "family_note": c["family"].note,
            "penalty_hours": r.penalty_hours, "penalty_safety": r.penalty_safety,
            "final_score": r.final_score, "eligible": r.eligible})
    return pd.DataFrame(recs)


def build_context(opps: list[Opportunity], norm: dict) -> Context:
    """The scoring context from what staff have decided and how many students are in play for each listing."""
    from . import applications, db
    try:
        decisions, load = db.list_decisions(), applications.load_by_listing()
    except Exception:  # no database yet: score without them
        decisions, load = [], {}
    return Context.build(opps, norm, decisions=decisions, load=load)


def score_all() -> list[MatchRow]:
    students, opps, norm = load_clean()
    enc = get_encoder()
    ov = opp_vectors(opps, norm, enc)
    ctx = build_context(opps, norm)
    rows: list[MatchRow] = []
    for s in students:
        rows += score_student(s, opps, norm, enc, ov, ctx)
    PATHS["pair_scores"].parent.mkdir(parents=True, exist_ok=True)
    rows_to_frame(rows).to_csv(PATHS["pair_scores"], index=False, lineterminator="\n")
    return rows


def main() -> None:
    rows = score_all()
    print(f"scored {len(rows)} pairs ({sum(r.eligible for r in rows)} eligible)")


if __name__ == "__main__":
    main()
