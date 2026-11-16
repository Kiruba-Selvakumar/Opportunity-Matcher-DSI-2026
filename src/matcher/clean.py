"""Clean the raw files into validated models. Never drops a record."""
from __future__ import annotations

import json
import re
from collections import Counter

import pandas as pd
from pydantic import ValidationError

from .config import OPENINGS_DEFAULT, PATHS
from .parse_text import parse_english, parse_student_text, split_required, split_skill_phrases
from .privacy import split_contacts
from .schema import Opportunity, Student


def _blank(x) -> bool:
    return x is None or (isinstance(x, float) and pd.isna(x)) or str(x).strip() == ""


def _s(x) -> str:
    return "" if _blank(x) else str(x).strip()


def _num(s: str) -> float | None:
    m = re.search(r"\d+(?:\.\d+)?", s.replace(",", ""))
    return float(m.group()) if m else None


def parse_cgpa(text) -> float | None:
    t = _s(text).lower()
    if not t:
        return None
    n = _num(t)
    if n is None:
        return None
    if "%" in t:
        return round(min(10.0, n / 9.5), 1)
    return round(min(10.0, n), 1)


def parse_budget(text) -> int | None:
    t = _s(text).lower()
    if not t:
        return None
    if t in {"nil", "no money", "none", "zero", "0"}:
        return 0
    t = t.replace(",", "").replace("rs.", "").replace("rs", "").replace("₹", "").replace("can manage", "")
    m = re.search(r"(\d+(?:\.\d+)?)\s*(k)?\s*(?:-|to)\s*(\d+(?:\.\d+)?)\s*(k)?", t)
    if m:
        k = m.group(2) or m.group(4)
        return int(float(m.group(1)) * (1000 if k else 1))
    m = re.search(r"(\d+(?:\.\d+)?)\s*(k)?", t)
    if m:
        return int(float(m.group(1)) * (1000 if m.group(2) else 1))
    return 0 if re.search(r"\b(nil|no money)\b", t) else None


def parse_relocate(text) -> bool | None:
    t = _s(text).lower()
    if t in {"yes", "y", "ok"}:
        return True
    if t in {"no", "n"}:
        return False
    return None


def parse_languages(text) -> list[str]:
    t = _s(text).lower()
    return [lang for lang in ("Telugu", "English", "Hindi") if lang.lower() in t]


def parse_family_limits(text) -> list[str]:
    t = _s(text).lower()
    out = []
    if "near" in t and "home" in t:
        out.append("near_home_only")
    if "night" in t:
        out.append("no_night_shift")
    if "safe" in t:
        out.append("safe_workplace_required")
    return out


def parse_pay(text) -> tuple[int | None, int | None]:
    t = _s(text).lower().replace("₹", " ").replace("rs.", " ").replace("rs", " ").replace(",", "")
    if not t or "not disclosed" in t:
        return (None, None)
    if "lpa" in t:
        m = re.search(r"(\d+(?:\.\d+)?)\s*(?:-|to)\s*(\d+(?:\.\d+)?)", t)
        if m:
            return (int(round(float(m.group(1)) * 100000)), int(round(float(m.group(2)) * 100000)))
        n = _num(t)
        return (None, None) if n is None else (int(round(n * 100000)),) * 2
    m = re.search(r"(\d+(?:\.\d+)?)\s*(k)?", t)
    if not m:
        return (None, None)
    val = float(m.group(1)) * (1000 if m.group(2) else 1)
    if "month" in t or "stipend" in t:
        val *= 12
    return (int(round(val)),) * 2


def parse_upfront(text) -> int:
    t = _s(text).lower().replace(",", "").replace("rs.", "").replace("rs", "").replace("₹", "")
    if not t or t in {"free", "0", "nil", "none"}:
        return 0
    m = re.search(r"(\d+(?:\.\d+)?)\s*(k)?", t)
    return int(float(m.group(1)) * (1000 if m.group(2) else 1)) if m else 0


def parse_yes_no(text) -> bool:
    return _s(text).lower() in {"yes", "y", "true", "1"}


def parse_program(text) -> str:
    """"Get Skills" (or skills, training) is the skill-building program. Everything else is Placements."""
    t = _s(text).lower()
    return "get_skills" if "skill" in t or "training" in t else "placements"


def parse_date(text) -> str | None:
    """A YYYY-MM-DD date, or None when blank or not a real date."""
    from datetime import date
    t = _s(text)
    try:
        return date.fromisoformat(t).isoformat() if t else None
    except ValueError:
        return None


def parse_int(text) -> int | None:
    t = _s(text)
    if not t:
        return None
    n = _num(t)
    return None if n is None else int(n)


def clean_student(row: dict, known_names: list[str] | None = None) -> Student:
    missing: list[str] = []
    cgpa = parse_cgpa(row.get("cgpa_text"))
    if cgpa is None:
        missing.append("cgpa")
    backlogs = parse_int(row.get("backlogs"))
    if backlogs is None:
        missing.append("backlogs")
    parsed = parse_student_text(_s(row.get("skills_text")), _s(row.get("english_text")), known_names)
    english = parsed["english_level"] or parse_english(_s(row.get("english_text")))
    if english is None:
        missing.append("english_level")
    relocate = parse_relocate(row.get("can_relocate_text"))
    if relocate is None:
        missing.append("can_relocate")
    budget = parse_budget(row.get("budget_text"))
    if budget is None:
        missing.append("budget")
    return Student(
        student_id=row["student_id"], branch=row["branch"], college_town=row["college_town"],
        grad_year=int(row["grad_year"]), college=_s(row.get("college_name")), program=parse_program(row.get("program")),
        cgpa=cgpa, backlogs=backlogs, skills_raw=parsed["skills_raw"],
        projects=parsed["projects"], english_level=english, languages=parse_languages(row.get("languages_text")),
        can_relocate=relocate, budget=budget, family_limits=parse_family_limits(row.get("family_limits_text")),
        missing_fields=missing, parse_method=parsed["parse_method"])


def clean_opportunity(row: dict) -> Opportunity:
    missing: list[str] = []
    lo, hi = parse_pay(row.get("pay_text"))
    if lo is None and row.get("type") == "job":
        missing.append("pay")
    required, nice = split_required(_s(row.get("required_skills_text")))
    mode = _s(row.get("mode")).lower()
    city = "Remote" if mode == "remote" else _s(row.get("city"))
    return Opportunity(
        opp_id=row["opp_id"], type=row["type"], title=_s(row.get("title")), org_name=_s(row.get("org_name")),
        job_family=_s(row.get("job_family")), required_skills_raw=required + [n for n in nice if n not in required],
        nice_to_have=nice, openings=OPENINGS_DEFAULT.get(_s(row.get("type")), 1),
        city=city, mode=mode, pay_min=lo, pay_max=hi, upfront_cost=parse_upfront(row.get("upfront_cost_text")),
        hours_per_week=int(row["hours_per_week"]), night_shift=parse_yes_no(row.get("night_shift")),
        safety_score=int(row["safety_score"]), languages_required=parse_languages(row.get("languages_required_text")),
        description=_s(row.get("description")), missing_fields=missing, parse_method="rule",
        apply_by=parse_date(row.get("apply_by")),
        starts_on=parse_date(row.get("starts_on")), duration_weeks=parse_int(row.get("duration_weeks")),
        batch_every_weeks=parse_int(row.get("batch_every_weeks")) or 0)


def clean_all() -> dict:
    """Read raw files, write clean files, contacts and the report. Returns the report."""
    raw_s = pd.read_csv(PATHS["students_raw"], dtype=str, keep_default_na=False)
    raw_o = pd.read_csv(PATHS["opportunities_raw"], dtype=str, keep_default_na=False)

    contacts, raw_s_clean = split_contacts(raw_s)
    PATHS["contacts"].parent.mkdir(parents=True, exist_ok=True)
    contacts.to_csv(PATHS["contacts"], index=False, lineterminator="\n")
    names = contacts["name"].tolist()

    students, s_failed = [], []
    for row in raw_s_clean.to_dict("records"):
        try:
            students.append(clean_student(row, names))
        except (ValidationError, ValueError, KeyError) as e:
            s_failed.append({"id": row.get("student_id"), "error": str(e)[:200]})
    opps, o_failed = [], []
    for row in raw_o.to_dict("records"):
        try:
            opps.append(clean_opportunity(row))
        except (ValidationError, ValueError, KeyError) as e:
            o_failed.append({"id": row.get("opp_id"), "error": str(e)[:200]})

    PATHS["students"].parent.mkdir(parents=True, exist_ok=True)
    PATHS["students"].write_text(json.dumps([s.model_dump() for s in students], indent=1))
    PATHS["opportunities"].write_text(json.dumps([o.model_dump() for o in opps], indent=1))

    report = {
        "students": {"records": len(students), "failed": s_failed,
                     "missing_per_field": dict(Counter(f for s in students for f in s.missing_fields)),
                     "parse_method": dict(Counter(s.parse_method for s in students))},
        "opportunities": {"records": len(opps), "failed": o_failed,
                          "missing_per_field": dict(Counter(f for o in opps for f in o.missing_fields)),
                          "parse_method": dict(Counter(o.parse_method for o in opps))},
    }
    PATHS["cleaning_report"].write_text(json.dumps(report, indent=1))
    return report


def main() -> None:
    r = clean_all()
    print(f"cleaned {r['students']['records']} students and {r['opportunities']['records']} opportunities")


if __name__ == "__main__":
    main()
