"""Data contracts. See IMPLEMENTATION_PLAN.md section 4."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator

Branch = Literal["CSE", "CSE (AI and ML)", "CSE (Data Science)", "IT", "ECE", "EEE"]
Language = Literal["English", "Telugu", "Hindi"]
FamilyLimit = Literal["no_night_shift", "near_home_only", "safe_workplace_required"]
ParseMethod = Literal["rule", "llm"]
Program = Literal["placements", "get_skills"]


class Student(BaseModel):
    student_id: str
    branch: Branch
    college_town: str
    grad_year: int
    college: str = ""
    program: Program = "placements"          # the NGO program the student came through
    cgpa: float | None = Field(default=None, ge=0, le=10)
    backlogs: int | None = None
    skills_raw: list[str] = []
    projects: int = 0
    english_level: Literal["basic", "intermediate", "fluent"] | None = None
    languages: list[Language] = []
    can_relocate: bool | None = None
    budget: int | None = None
    family_limits: list[FamilyLimit] = []
    missing_fields: list[str] = []
    parse_method: ParseMethod = "rule"


class Opportunity(BaseModel):
    opp_id: str
    type: Literal["job", "training", "mentor"]
    title: str
    org_name: str
    job_family: str
    required_skills_raw: list[str] = []
    city: str
    mode: Literal["onsite", "hybrid", "remote"]
    pay_min: int | None = None
    pay_max: int | None = None
    upfront_cost: int = 0
    hours_per_week: int
    night_shift: bool = False
    safety_score: int = Field(ge=1, le=5)
    languages_required: list[Language] = []
    nice_to_have: list[str] = []          # raw phrases the employer marked "is a plus"
    description: str = ""
    openings: int = 1
    missing_fields: list[str] = []
    parse_method: ParseMethod = "rule"
    apply_by: str | None = None              # last day to show interest (YYYY-MM-DD)
    starts_on: str | None = None             # training: first batch starts (YYYY-MM-DD)
    duration_weeks: int | None = None        # training: how long one batch runs
    batch_every_weeks: int = 0               # training: a new batch every N weeks (0 = one batch only)

    @model_validator(mode="after")
    def remote_city(self):
        if self.mode == "remote" and self.city != "Remote":
            raise ValueError("remote opportunities must have city 'Remote'")
        return self


class CheckResult(BaseModel):
    status: Literal["pass", "fail", "unknown"]
    note: str = ""


class MatchRow(BaseModel):
    student_id: str
    opp_id: str
    type: Literal["job", "training", "mentor"]
    title: str
    org_name: str
    city: str
    mode: str
    pay_min: int | None = None
    pay_max: int | None = None
    upfront_cost: int = 0
    skill_sim: float
    coverage: float
    overlap: list[str] = []
    missing: list[str] = []
    base_score: float
    checks: dict[str, CheckResult]
    penalty_hours: float = 0.0
    penalty_safety: float = 0.0
    final_score: float
    eligible: bool
    related: list[dict] = []              # [{"have", "need", "credit"}] skills that counted partly
    adjustments: dict[str, float] = {}    # soft fit terms, congestion and prior, each with its sign
    crowded: bool = False
    prior_note: str | None = None
    nice_missing: list[str] = []
    teaches: list[str] = []                # training only: gap skills this teaches
    upskill: dict | None = None            # job only: how easily the missing skills can be closed (see upskill.py)
    standing: dict | None = None           # where this student ranks among eligible students for the listing
    ml: float | None = None                # learned chance that staff or the employer say yes (see learn.py)

    def unknown_count(self) -> int:
        return sum(1 for c in self.checks.values() if c.status == "unknown")


class TopMatch(BaseModel):
    rank: int
    opp_id: str
    title: str
    org_name: str = ""
    type: Literal["job", "training", "mentor"]
    city: str
    mode: str = ""
    final_score: float
    overlap: list[str] = []
    missing: list[str] = []
    checks: dict[str, CheckResult]
    warnings: list[str] = []
    reason: str
    reason_method: Literal["template", "llm"] = "template"
    headline: str = ""                     # student card: how this match compares with the others
    related: list[dict] = []
    crowded: bool = False
    prior_note: str | None = None
    fit: str = ""
    gap_closers: list[dict] = []
    teaches: list[str] = []
    upskill: dict | None = None
    standing: dict | None = None
    ml: float | None = None
    apply_by: str | None = None


class Decision(BaseModel):
    id: int | None = None
    created_at: str | None = None
    student_id: str
    opp_id: str
    rank: int | None = None
    final_score: float | None = None
    decision: Literal["accept", "reject", "flag"]
    reject_reason: str | None = None
    note: str | None = None
    what_if: bool = False
    seconds_to_decide: float | None = None
    decided_by: str | None = None

    @model_validator(mode="after")
    def needs(self):
        if self.decision == "flag" and not (self.note or "").strip():
            raise ValueError("a flag needs a note")
        if self.decision == "reject" and not (self.reject_reason or "").strip():
            raise ValueError("a reject needs a reason")
        return self
