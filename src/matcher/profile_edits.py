"""What a student may change about their own profile. The pipeline data is never touched. Edits are laid on top."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from . import auth
from .schema import MatchRow, Student
from .skills import load_vocab
from .store import connect


class ProfileEdit(BaseModel):
    """Only the fields that are sent are changed."""
    model_config = ConfigDict(extra="forbid")
    can_relocate: Literal["yes", "no", "unknown"] | None = None
    budget: int | None = Field(default=None, ge=0, le=10_000_000)
    family_limits: list[Literal["no_night_shift", "near_home_only", "safe_workplace_required"]] | None = Field(default=None, max_length=3)
    languages: list[Literal["English", "Telugu", "Hindi"]] | None = Field(default=None, max_length=3)
    english_level: Literal["basic", "intermediate", "fluent"] | None = None
    extra_skills: list[str] | None = Field(default=None, max_length=30)


EDITABLE = ("can_relocate", "budget", "family_limits", "languages", "english_level", "extra_skills")


def validate_skills(skills: list[str]) -> list[str]:
    vocab = set(load_vocab())
    bad = [s for s in skills if s not in vocab]
    if bad:
        raise ValueError(f"{bad[0]} is not in the skill list.")
    return list(dict.fromkeys(skills))


def get_edits(student_id: str, path: Path | str | None = None) -> dict:
    c = connect(path)
    try:
        r = c.execute("SELECT data, updated_at FROM student_edits WHERE student_id = ?", (student_id,)).fetchone()
        return {**json.loads(r["data"]), "_updated_at": r["updated_at"]} if r else {}
    finally:
        c.close()


def all_edits(path: Path | str | None = None) -> dict[str, dict]:
    c = connect(path)
    try:
        return {r["student_id"]: {**json.loads(r["data"]), "_updated_at": r["updated_at"]}
                for r in c.execute("SELECT student_id, data, updated_at FROM student_edits")}
    finally:
        c.close()


def save_edits(student_id: str, patch: ProfileEdit, user_id: int | None = None, path: Path | str | None = None) -> dict:
    sent = {k: v for k, v in patch.model_dump().items() if k in patch.model_fields_set}
    if "extra_skills" in sent and sent["extra_skills"] is not None:
        sent["extra_skills"] = validate_skills(sent["extra_skills"])
    if not sent:
        raise ValueError("Nothing to change.")
    cur = {k: v for k, v in get_edits(student_id, path).items() if not k.startswith("_")}
    cur.update(sent)
    c = connect(path)
    try:
        c.execute("INSERT INTO student_edits (student_id, data, updated_at, updated_by) VALUES (?,?,?,?) "
                  "ON CONFLICT(student_id) DO UPDATE SET data = excluded.data, updated_at = excluded.updated_at, updated_by = excluded.updated_by",
                  (student_id, json.dumps(cur), auth.iso(auth.now()), user_id))
    finally:
        c.close()
    return get_edits(student_id, path)


def apply_edits(student: Student, edits: dict) -> Student:
    """Return the student as they are now: the pipeline data with their own changes on top."""
    if not edits:
        return student
    data = student.model_dump()
    missing = set(data["missing_fields"])
    if "can_relocate" in edits:
        v = {"yes": True, "no": False, "unknown": None}[edits["can_relocate"]]
        data["can_relocate"] = v
        (missing.discard if v is not None else missing.add)("can_relocate")
    if "budget" in edits:
        data["budget"] = edits["budget"]
        (missing.discard if edits["budget"] is not None else missing.add)("budget")
    if edits.get("family_limits") is not None:
        data["family_limits"] = edits["family_limits"]
    if edits.get("languages") is not None:
        data["languages"] = edits["languages"]
    if "english_level" in edits:
        data["english_level"] = edits["english_level"]
        (missing.discard if edits["english_level"] else missing.add)("english_level")
    data["missing_fields"] = sorted(missing)
    return Student(**data)


def edited_fields(edits: dict) -> list[str]:
    return [k for k in EDITABLE if k in edits]


def completeness(student: Student, skills: list[str], rows: list[MatchRow]) -> dict:
    """A plain checklist. Each open item says how many matches it is holding back."""
    def held(check: str) -> int:
        return sum(1 for r in rows if r.checks[check].status == "unknown")
    items = [
        {"field": "can_relocate", "label": "Whether you can move for a job", "done": student.can_relocate is not None,
         "impact": held("location")},
        {"field": "budget", "label": "How much you can spend up front", "done": student.budget is not None, "impact": held("budget")},
        {"field": "english_level", "label": "Your English level", "done": student.english_level is not None, "impact": 0},
        {"field": "languages", "label": "The languages you speak", "done": bool(student.languages), "impact": 0},
        {"field": "skills", "label": "At least 3 skills", "done": len(skills) >= 3, "impact": 0},
    ]
    done = sum(1 for i in items if i["done"])
    return {"percent": round(100 * done / len(items)), "items": items}
