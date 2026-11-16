"""Short reasons for each match. Template first; an optional LLM sentence is fact-checked."""
from __future__ import annotations

import json
import re

from . import llm
from .config import PATHS
from .schema import Opportunity, Student, TopMatch
from .skills import load_vocab

CITIES = ["Warangal", "Khammam", "Karimnagar", "Nizamabad", "Nalgonda", "Mahabubnagar", "Guntur", "Vijayawada",
          "Tirupati", "Visakhapatnam", "Hyderabad", "Bengaluru", "Chennai", "Pune"]

LLM_SYSTEM = (
    "Write one plain sentence (under 30 words) telling a placement officer why this opportunity fits the student.\n"
    "Use only the facts given. Do not add skills, cities, numbers or companies that are not in the facts.\n"
    'Return JSON: {"reason": "..."}'
)


def _join(items: list[str]) -> str:
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


def _strong_related(m) -> dict | None:
    """A related skill is mentioned only when it earns at least half credit. Weaker same-area credit stays in the breakdown."""
    return next((r for r in (getattr(m, "related", None) or []) if r["credit"] >= 0.5), None)


def template_reason(m, student: Student, opp: Opportunity) -> str:
    """m is a TopMatch or MatchRow (it needs overlap, missing, type, city, mode and checks)."""
    parts: list[str] = []
    builds = False
    if m.type == "training" and getattr(m, "teaches", None):
        parts.append(f"Teaches {_join(m.teaches[:3])}, which your best matches ask for")
        builds = True
    elif m.overlap:
        parts.append(f"Matches your {_join(m.overlap[:3])} skills")
        strong = _strong_related(m)
        if strong:
            parts.append(f"Your {strong['have']} also counts for {strong['need']}")
    elif _strong_related(m) and m.type != "training":
        r = _strong_related(m)
        parts.append(f"Your {r['have']} counts for {r['need']}")
    elif m.type == "training" and m.missing:
        parts.append(f"Builds skills in {m.missing[0]}")
        builds = True
    else:
        parts.append("Weak skill match")
    if m.mode == "remote" or opp.city == "Remote":
        parts.append("Remote, no need to move")
    elif opp.city == student.college_town:
        parts.append(f"In {student.college_town}, no need to move")
    else:
        parts.append(f"Needs a move to {opp.city}")
    if opp.upfront_cost > 0:
        parts.append(f"Costs Rs {opp.upfront_cost}")
    elif opp.type != "job":
        parts.append("Free")
    if opp.type == "job" and opp.pay_min is not None and opp.pay_max is not None:
        parts.append(f"Pay about {(opp.pay_min + opp.pay_max) / 2 / 100000:.1f} LPA")
    if m.missing and not builds:
        parts.append(f"Learn {m.missing[0]} to improve fit")
    st = getattr(m, "standing", None)
    if st and st["of"] >= 5 and st["rank"] / st["of"] <= 0.2:
        parts.append(f"In the top {-(-100 * st['rank'] // st['of'])}% of the {st['of']} students it fits"
                     if st["rank"] > 1 else f"The strongest of the {st['of']} students it fits")
    if getattr(m, "crowded", False):
        parts.append("Many students have already applied")
    if getattr(m, "prior_note", None):
        parts.append(m.prior_note)
    for c in m.checks.values():
        if c.status == "unknown":
            parts.append(f"Check: {c.note}")
    return ". ".join(parts) + "."


ORDINAL = {1: "first", 2: "second", 3: "third", 4: "fourth", 5: "fifth"}


def _pay(opp: Opportunity) -> float | None:
    if opp.type == "job" and opp.pay_min is not None and opp.pay_max is not None:
        return (opp.pay_min + opp.pay_max) / 2
    return None


def _skills(n: int) -> str:
    return f"{n} skill" if n == 1 else f"{n} skills"


def _job_line(m, matches: list, opps_by_id: dict[str, Opportunity]) -> list[str]:
    opp = opps_by_id[m.opp_id]
    pay = _pay(opp)
    earlier = next((x for x in matches if x.type == "job" and x.rank < m.rank
                    and opps_by_id[x.opp_id].job_family == opp.job_family), None)
    if earlier:
        line = f"The same kind of role as your {ORDINAL.get(earlier.rank, 'earlier')} match"
        other = _pay(opps_by_id[earlier.opp_id])
        if pay and other and pay != other:
            line += ", and it pays more" if pay > other else ", but it pays less"
        if m.missing:
            return [line, f"It also asks for {_join(m.missing[:2])}, which you don't have yet"]
        return [line, "You already have every skill it asks for"]
    if not m.missing:
        parts = ["You already have every skill this role asks for, so you can apply as you are"]
    elif m.fit in ("Stretch", "Possible fit") or len(m.overlap) < len(m.missing):
        total = len(m.overlap) + len(m.missing)
        if m.overlap:
            parts = [f"A stretch: you have {len(m.overlap)} of the {_skills(total)} it asks for"]
        elif getattr(m, "related", None):
            parts = ["A stretch: you don't have the skills it asks for yet, but some of yours are close"]
        else:
            parts = ["A stretch: you don't have the skills it asks for yet"]
    elif len(m.missing) == 1:
        parts = ["One skill away from a full fit"]
    else:
        parts = [f"A good fit on your current skills, with {len(m.missing)} more skills to learn"]
    pays = [p for p in (_pay(opps_by_id[x.opp_id]) for x in matches if x.type == "job") if p is not None]
    if pay is not None and len(pays) >= 3 and pays.count(pay) == 1:
        if pay == max(pays):
            parts.append("It pays the most of your job matches")
        elif pay == min(pays):
            parts.append("It pays the least of your job matches")
    return parts


def _support_line(m, matches: list) -> list[str]:
    """Training and mentors: say how they help with what the student's job matches ask for."""
    jobs = [x for x in matches if x.type == "job"]
    gaps: list[str] = []
    for x in jobs:
        gaps += [s for s in x.missing if s not in gaps]
    what = "training" if m.type == "training" else "mentor"
    verb = "Teaches" if m.type == "training" else "A mentor who can help you learn"
    if m.type == "training" and getattr(m, "teaches", None):
        return [f"Teaches {_join(m.teaches[:3])}, which the jobs that fit you best ask for"]
    helps = [s for s in m.missing if s in gaps]
    if helps:
        return [f"{verb} {_join(helps[:3])}, which your job matches ask for"]
    if m.missing and not jobs:
        return [f"{verb} {_join(m.missing[:2])}"]
    if m.missing:
        return [f"A {what} in skills outside your job matches, such as {m.missing[0]}"]
    return [f"A {what} in skills you already have, to take them further"]


def headline(m, matches: list, opps_by_id: dict[str, Opportunity]) -> str:
    """One line for the student's card. The tags under it already list skills, place, pay and cost,
    so this says what they cannot: how this match compares with the student's other matches."""
    parts = _job_line(m, matches, opps_by_id) if m.type == "job" else _support_line(m, matches)
    return ". ".join(parts) + "."


def facts_for(m, opp: Opportunity) -> dict:
    pay = None
    if opp.type == "job" and opp.pay_min is not None and opp.pay_max is not None:
        pay = round((opp.pay_min + opp.pay_max) / 2 / 100000, 1)
    return {"title": opp.title, "type": opp.type, "city": opp.city, "mode": opp.mode, "overlap": list(m.overlap),
            "missing": list(m.missing), "pay_lpa": pay, "upfront_cost": opp.upfront_cost,
            "check_notes": [c.note for c in m.checks.values() if c.note]}


def _mentions(text: str, skill: str) -> bool:
    flags = 0 if len(skill) <= 3 else re.IGNORECASE
    return re.search(r"(?<![\w.+#])" + re.escape(skill) + r"(?![\w+#])", text, flags) is not None


def fact_check(reason: str, facts: dict, vocab: list[str]) -> bool:
    if not reason or len(reason.split()) > 40:
        return False
    allowed = set(facts.get("overlap", [])) | set(facts.get("missing", []))
    title = facts.get("title", "")
    allowed |= {s for s in vocab if _mentions(title, s)}
    for s in vocab:
        if s not in allowed and _mentions(reason, s):
            return False
    for city in CITIES:
        if city != facts.get("city") and re.search(r"\b" + city + r"\b", reason, re.IGNORECASE):
            return False
    ok_nums = set(range(0, 6)) | {len(facts.get("overlap", [])), len(facts.get("missing", []))}
    if facts.get("pay_lpa") is not None:
        ok_nums |= {facts["pay_lpa"], round(facts["pay_lpa"])}
    cost = facts.get("upfront_cost") or 0
    ok_nums |= {cost, cost / 1000}
    for n in re.findall(r"\d+(?:\.\d+)?", reason.replace(",", "")):
        if not any(abs(float(n) - float(x)) < 1e-6 for x in ok_nums):
            return False
    return True


def llm_reason(facts: dict, vocab: list[str]) -> str | None:
    res = llm.complete_json(LLM_SYSTEM, json.dumps(facts), {"reason": "str"}, known_names=[])
    if not res or not isinstance(res.get("reason"), str):
        return None
    return res["reason"] if fact_check(res["reason"], facts, vocab) else None


def fill_reasons(student: Student, matches: list[TopMatch], opps_by_id: dict[str, Opportunity],
                 vocab: list[str] | None = None) -> list[TopMatch]:
    vocab = vocab or load_vocab()
    use_llm = llm.provider() != "none"
    for m in matches:
        opp = opps_by_id[m.opp_id]
        text = llm_reason(facts_for(m, opp), vocab) if use_llm else None
        if text:
            m.reason, m.reason_method = text, "llm"
        else:
            m.reason, m.reason_method = template_reason(m, student, opp), "template"
        m.headline = headline(m, matches, opps_by_id)
    return matches


def explain_all() -> dict:
    from .schema import Student as S
    top = json.loads(PATHS["top5"].read_text())
    students = {d["student_id"]: S(**d) for d in json.loads(PATHS["students"].read_text())}
    opps = {d["opp_id"]: Opportunity(**d) for d in json.loads(PATHS["opportunities"].read_text())}
    vocab = load_vocab()
    out = {}
    for sid, items in top.items():
        ms = fill_reasons(students[sid], [TopMatch(**i) for i in items], opps, vocab)
        out[sid] = [m.model_dump() for m in ms]
    PATHS["top5"].write_text(json.dumps(out, indent=1))
    return out


def main() -> None:
    out = explain_all()
    print(f"wrote reasons for {len(out)} students")


if __name__ == "__main__":
    main()
