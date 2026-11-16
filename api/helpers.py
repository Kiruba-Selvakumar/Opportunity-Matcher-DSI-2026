"""Pure logic for the dashboard API. Nothing here needs a running server."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from matcher.config import PATHS
from matcher.embed import get_encoder
from matcher.explain import fill_reasons
from matcher.rank import to_top_matches, top_k
from matcher.recommend import close_the_gap, fit_label
from matcher import ats, config, contacts, profile_edits, resumes, settings
from matcher.parse_text import extract_resume, parse_english
from matcher.privacy import candidate_code
from matcher.schema import MatchRow, Opportunity, Student, TopMatch
from matcher.skills import normalize_student
from matcher.score import score_student

from .state import REQUIRED, NotReady, State, load_state  # noqa: F401  (re-exported for the server and tests)


def student_list(st: State) -> list[dict]:
    out = []
    cvs = resumes.all_meta()
    agreed = contacts.opted_in()
    for s in st.students.values():
        picks = top_k(st.rows_by_student[s.student_id], min_score=config.MIN_SHOW_SCORE)
        e = st.edits.get(s.student_id, {})
        cv = cvs.get(s.student_id)
        out.append({
            "id": s.student_id, "branch": s.branch, "town": s.college_town, "college": s.college, "program": s.program,
            "has_resume": cv is not None, "resume_score": cv["quality"] if cv else None, "whatsapp": s.student_id in agreed,
            "label": f"{s.student_id} · {s.branch} · {s.college_town}",
            "cgpa": s.cgpa, "grad_year": s.grad_year, "can_relocate": s.can_relocate, "budget": s.budget,
            "family_limits": s.family_limits, "missing_fields": s.missing_fields,
            "skills": st.norm["students"][s.student_id]["skills"],
            "n_matches": len(picks), "best_match": picks[0].title if picks else None,
            "candidate_code": candidate_code(s.student_id, settings.candidate_salt()),
            "edited": profile_edits.edited_fields(e),
        })
    return out


def student_profile(st: State, sid: str) -> dict:
    s = st.students[sid]
    n = st.norm["students"][sid]
    e = st.edits.get(sid, {})
    cv = resumes.meta(sid)
    return {**s.model_dump(), "skills": n["skills"], "unmatched": n["unmatched"],
            "edited_fields": profile_edits.edited_fields(e), "edited_at": e.get("_updated_at"),
            "resume": resume_summary(cv, n["skills"]), "consent": contacts.consent(sid)}


def resume_summary(cv: dict | None, skills: list[str] | None = None) -> dict | None:
    """What anyone allowed to see a resume sees about it. Never the text."""
    if cv is None:
        return None
    rep = cv["report"] or {}
    found = rep.get("skills", [])
    return {"uploaded_at": cv["uploaded_at"], "source": cv["source"], "pages": cv["pages"], "score": cv["quality"],
            "grade": rep.get("grade"), "parts": rep.get("parts", {}), "sections": rep.get("sections", []), "tips": rep.get("tips", []),
            "skills": found, "not_in_profile": [k for k in found if skills is not None and k not in skills]}


def ats_for(st: State, sid: str, oid: str) -> dict | None:
    cv = resumes.meta(sid)
    if cv is None or not cv["report"] or oid not in st.opps:
        return None
    n = st.norm["opportunities"][oid]
    return ats.for_listing(cv["report"], n["skills"], n.get("nice", []))


def enrich(st: State, m: dict | TopMatch, sid: str | None = None) -> dict:
    d = m.model_dump() if isinstance(m, TopMatch) else dict(m)
    o = st.opps[d["opp_id"]]
    d.update(org_name=o.org_name, mode=o.mode, upfront_cost=o.upfront_cost, hours_per_week=o.hours_per_week,
             night_shift=o.night_shift, safety_score=o.safety_score, pay_min=o.pay_min, pay_max=o.pay_max,
             apply_by=o.apply_by, starts_on=o.starts_on, duration_weeks=o.duration_weeks)
    row = st.row(sid, d["opp_id"]) if sid else None
    if row:
        d["breakdown"] = breakdown(row)
    if sid:
        d["ats"] = ats_for(st, sid, d["opp_id"])
    return d


def breakdown(r: MatchRow) -> dict:
    """The numbers behind a score, so staff can see how it was made."""
    return {"skill_sim": r.skill_sim, "coverage": r.coverage, "base_score": r.base_score,
            "weight_sim": config.WEIGHT_SIM, "weight_coverage": config.WEIGHT_COVERAGE,
            "penalty_hours": r.penalty_hours, "penalty_safety": r.penalty_safety, "final_score": r.final_score,
            "related": r.related, "adjustments": r.adjustments, "crowded": r.crowded, "prior_note": r.prior_note,
            "upskill": r.upskill, "standing": r.standing, "ml": r.ml}


def scoring_config() -> dict:
    return {"weight_sim": config.WEIGHT_SIM, "weight_coverage": config.WEIGHT_COVERAGE,
            "relocation_cost": config.RELOCATION_COST, "long_hours": config.LONG_HOURS,
            "penalty_long_hours": config.PENALTY_LONG_HOURS, "penalty_safety_3": config.PENALTY_SAFETY_3,
            "penalty_safety_low": config.PENALTY_SAFETY_LOW, "top_k": config.TOP_K}


def default_matches(st: State, sid: str) -> list[dict]:
    return [enrich(st, m, sid) for m in st.matches(sid)]


def apply_overrides(s: Student, ov: dict) -> Student:
    data = s.model_dump()
    if "can_relocate" in ov:
        data["can_relocate"] = {"yes": True, "no": False, "unknown": None, None: None}.get(ov["can_relocate"])
    if "budget" in ov:
        data["budget"] = ov["budget"]
    if "family_limits" in ov and ov["family_limits"] is not None:
        data["family_limits"] = list(ov["family_limits"])
    return Student(**data)


def score_rows(st: State, sid: str, ov: dict | None = None) -> list[MatchRow]:
    if not ov:
        return st.rows_by_student[sid]
    s = apply_overrides(st.students[sid], ov)
    return score_student(s, list(st.opps.values()), st.norm, st.enc, st.opp_vecs, st.ctx)


def whatif_matches(st: State, sid: str, ov: dict) -> list[dict]:
    s = apply_overrides(st.students[sid], ov)
    rows = score_rows(st, sid, ov)
    ms = to_top_matches(top_k(rows, min_score=config.MIN_SHOW_SCORE))
    for m in ms:
        m.gap_closers = close_the_gap(rows, st.norm, m.missing, exclude=m.opp_id) if m.type == "job" else []
        m.fit = fit_label(m.final_score, bool(m.gap_closers))
    ms = fill_reasons(s, ms, st.opps, st.vocab)
    out = []
    for m in ms:
        d = enrich(st, m)
        d["breakdown"] = breakdown(next(r for r in rows if r.opp_id == m.opp_id))
        out.append(d)
    return out


def why_not(st: State, sid: str, ov: dict | None = None, n: int = 5) -> list[dict]:
    """High-skill opportunities that the hard filters removed."""
    rows = [r for r in score_rows(st, sid, ov) if not r.eligible]
    rows.sort(key=lambda r: (-r.base_score, r.opp_id))
    out = []
    for r in rows[:n]:
        fails = [{"check": k, "note": c.note} for k, c in r.checks.items() if c.status == "fail"]
        out.append({"opp_id": r.opp_id, "title": r.title, "type": r.type, "city": r.city,
                    "base_score": r.base_score, "overlap": r.overlap, "fails": fails})
    return out


def opportunity_list(st: State) -> list[dict]:
    out = []
    for o in st.opps.values():
        rows = st.rows_by_opp[o.opp_id]
        out.append({**o.model_dump(), "skills": st.norm["opportunities"][o.opp_id]["skills"],
                    "eligible_count": sum(r.eligible for r in rows), "load": st.ctx.load.get(o.opp_id, 0),  # type: ignore[union-attr]
                    "managed": o.opp_id.startswith("E"), "closing_soon": closing_soon(o.apply_by)})
    return out


def deadline_passed(apply_by: str | None) -> bool:
    from datetime import date
    return bool(apply_by) and date.fromisoformat(apply_by) < date.today()  # type: ignore[arg-type]


def interview_view(iv: dict, role: str) -> dict:
    """An interview as each side may see it. Employers get the candidate code, never the student ID; students never
    get the interviewer's email. Notes are for the NGO and the employer who held it."""
    from matcher import interviews as iv_mod
    d = {"id": iv["id"], "starts_at": iv["starts_at"], "when": iv_mod.words(iv["starts_at"]), "minutes": iv["minutes"],
         "mode": iv["mode"], "location": iv["location"], "meet_link": iv["meet_link"], "status": iv["status"],
         "interviewer": iv["interviewer"], "calendar": iv["calendar"], "notetaker": iv["notetaker"]}
    if role in ("ngo", "employer"):
        d.update(summary=iv["summary"], action_items=iv["action_items"], notes_source=iv["notes_source"],
                 interviewer_email=iv["interviewer_email"], application_id=iv["application_id"], opp_id=iv["opp_id"],
                 student_invited=iv["student_invited"])
    if role == "ngo":
        d.update(student_id=iv["student_id"], created_by=iv["created_by"])
    return d


def closing_soon(apply_by: str | None) -> bool:
    from datetime import date
    return bool(apply_by) and (date.fromisoformat(apply_by) - date.today()).days <= config.CLOSING_SOON_DAYS  # type: ignore[arg-type]


def _candidate(st: State, r: MatchRow) -> dict:
    s = st.students[r.student_id]
    a = ats_for(st, r.student_id, r.opp_id)
    return {"student_id": s.student_id, "branch": s.branch, "town": s.college_town, "cgpa": s.cgpa,
            "college": s.college, "program": s.program, "standing": r.standing, "ats": a["score"] if a else None,
            "final_score": r.final_score, "coverage": r.coverage, "overlap": r.overlap, "missing": r.missing,
            "checks": {k: c.model_dump() for k, c in r.checks.items()},
            "concerns": [f"{k}: {c.note}" for k, c in r.checks.items() if c.status == "unknown"],
            "needs_move": r.checks["location"].note.startswith("needs move")}


def opportunity_detail(st: State, oid: str, limit: int = 15) -> dict:
    o = st.opps[oid]
    rows = st.rows_by_opp[oid]
    elig = sorted((r for r in rows if r.eligible), key=lambda r: (-r.final_score, r.unknown_count(), r.student_id))
    removed: dict[str, int] = {}
    for r in rows:
        for k, c in r.checks.items():
            if c.status == "fail":
                removed[k] = removed.get(k, 0) + 1
    return {**o.model_dump(), "skills": st.norm["opportunities"][oid]["skills"], "eligible_count": len(elig),
            "total_students": len(rows), "removed_by": removed,
            "candidates": [_candidate(st, r) for r in elig[:limit]]}


RAW_FIELDS = ["skills_text", "cgpa_text", "backlogs", "english_text", "languages_text", "can_relocate_text",
              "budget_text", "family_limits_text"]


def raw_text(sid: str) -> dict | None:
    """The student's raw text fields. Name, phone and email are never included."""
    p = Path(PATHS["students_raw"])
    if not p.exists():
        return None
    df = pd.read_csv(p, dtype=str, keep_default_na=False)
    hit = df[df["student_id"] == sid]
    return None if hit.empty else {k: hit.iloc[0][k] for k in RAW_FIELDS}


def intake_student(body: dict, resume: dict) -> Student:
    """Build a student from pasted resume text plus the circumstances staff typed in."""
    rel = body.get("can_relocate")
    langs = [lang for lang in body.get("languages") or ["Telugu", "English"] if lang in ("English", "Telugu", "Hindi")]
    cgpa = body.get("cgpa") if body.get("cgpa") is not None else resume["cgpa"]
    english = body.get("english_level") or resume["english_level"]
    missing = [n for n, v in (("cgpa", cgpa), ("english_level", english), ("can_relocate", {"yes": True, "no": False}.get(rel)),
                              ("budget", body.get("budget"))) if v is None]
    return Student(student_id="NEW", branch=body.get("branch") or "CSE", college_town=body.get("college_town") or "Khammam",
                   grad_year=int(body.get("grad_year") or 2026), cgpa=cgpa, backlogs=body.get("backlogs"),
                   skills_raw=resume["skills_raw"], projects=resume["projects"], english_level=english, languages=langs,
                   can_relocate={"yes": True, "no": False}.get(rel), budget=body.get("budget"),
                   family_limits=body.get("family_limits") or [], missing_fields=missing, parse_method=resume["parse_method"])


def intake_parse(st: State, body: dict, resume_text: str) -> dict:
    resume = extract_resume(resume_text)
    s = intake_student(body, resume)
    n = normalize_student(s, st.enc)
    return {"student": s.model_dump(), "skills": n["skills"], "unmatched": n["unmatched"],
            "extracted": {"cgpa": resume["cgpa"], "projects": resume["projects"], "english_level": resume["english_level"],
                          "skills_found": resume["skills_raw"]}}


def intake_match(st: State, body: dict, resume_text: str) -> dict:
    parsed = intake_parse(st, body, resume_text)
    s = Student(**parsed["student"])
    norm = {"students": {"NEW": {"skills": parsed["skills"], "unmatched": parsed["unmatched"]}},
            "opportunities": st.norm["opportunities"]}
    rows = score_student(s, list(st.opps.values()), norm, st.enc, st.opp_vecs, st.ctx, in_field=False)
    picks = top_k(rows)
    ms = fill_reasons(s, to_top_matches(picks), st.opps, st.vocab)
    by = {r.opp_id: r for r in rows}
    out = []
    for m in ms:
        d = enrich(st, m)
        d["breakdown"] = breakdown(by[m.opp_id])
        out.append(d)
    return {**parsed, "matches": out}


def student_self(st: State, sid: str, apps: dict[str, dict] | None = None, saved: set[str] | None = None) -> dict:
    """What a student may see about themselves: their own profile and matches, and nothing about anyone else."""
    matches = default_matches(st, sid)
    for m in matches:
        m.pop("breakdown", None)
        a = (apps or {}).get(m["opp_id"])
        m["application"] = {"id": a["id"], "status": a["status"], "words": a["words"]} if a else None
        m["saved"] = m["opp_id"] in (saved or set())
    eligible = [r for r in st.rows_by_student[sid] if r.eligible]
    return {"profile": student_profile(st, sid), "matches": matches, "why_not": why_not(st, sid),
            "name": st.contacts.get(sid), "shown": len(matches), "eligible_total": len(eligible),
            "min_score": config.MIN_SHOW_SCORE}


def listing_row(st: State, oid: str) -> dict:
    o = st.opps[oid]
    return {"opp_id": oid, "title": o.title, "org_name": o.org_name, "type": o.type, "city": o.city, "mode": o.mode,
            "eligible_count": sum(r.eligible for r in st.rows_by_opp[oid])}


def employer_listing(st: State, oid: str, limit: int = 15) -> dict:
    """A listing for its owner. Candidates carry a code, never a name, student ID, budget or family limit."""
    d = opportunity_detail(st, oid, limit)
    salt = settings.candidate_salt()
    cands = [{"candidate_code": candidate_code(c["student_id"], salt), "branch": c["branch"], "town": c["town"],
              "cgpa": c["cgpa"], "final_score": c["final_score"], "coverage": c["coverage"],
              "overlap": c["overlap"], "missing": c["missing"]} for c in d["candidates"]]
    keep = ("opp_id", "type", "title", "org_name", "job_family", "city", "mode", "pay_min", "pay_max", "upfront_cost",
            "hours_per_week", "night_shift", "safety_score", "languages_required", "skills", "eligible_count",
            "total_students", "apply_by", "starts_on", "duration_weeks", "batch_every_weeks")
    return {**{k: d[k] for k in keep}, "candidates": cands}
