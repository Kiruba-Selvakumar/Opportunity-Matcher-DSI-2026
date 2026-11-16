"""Listings that employers post: validation, status flow, NGO review and conversion to a matchable Opportunity."""
from __future__ import annotations

import json
import re
import sqlite3
from datetime import date
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from . import auth
from .clean import clean_opportunity
from .privacy import EMAIL_RE, PHONE_RE, redact
from .schema import Opportunity
from .store import connect

STATUSES = ("draft", "pending", "active", "rejected", "closed")
CONTACT_WORDS = re.compile(r"\b(whatsapp|telegram|dm me|call me|contact me on|pay (?:first|first)|registration fee|security deposit)\b", re.I)


class ListingError(ValueError):
    """The change is not allowed. The message is safe to show."""


class ListingIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=3, max_length=80)
    type: Literal["job", "training", "mentor"] = "job"           # mentor: NGO admins only (the router checks)
    org_name: str = Field(min_length=2, max_length=80)
    description: str = Field(default="", max_length=1000)
    required_skills_text: str = Field(min_length=2, max_length=300)
    city: str = Field(default="", max_length=40)
    mode: Literal["onsite", "hybrid", "remote"] = "onsite"
    pay_text: str = Field(default="", max_length=60)
    upfront_cost_text: str = Field(default="0", max_length=40)
    hours_per_week: int = Field(default=40, ge=1, le=80)
    night_shift: bool = False
    languages: list[Literal["English", "Telugu", "Hindi"]] = ["English"]
    openings: int = Field(default=1, ge=1, le=50)
    apply_by: str | None = Field(default=None, max_length=10)          # last day students can show interest
    starts_on: str | None = Field(default=None, max_length=10)         # training: first batch
    duration_weeks: int | None = Field(default=None, ge=1, le=104)     # training: one batch
    batch_every_weeks: int = Field(default=0, ge=0, le=52)             # training: a new batch every N weeks

    @field_validator("title", "org_name", "description", "required_skills_text", "city", "pay_text", "upfront_cost_text")
    @classmethod
    def trim(cls, v: str) -> str:
        return re.sub(r"[ \t]+", " ", v.strip())

    @model_validator(mode="after")
    def city_rules(self):
        if self.mode == "remote":
            self.city = "Remote"
        elif not self.city or self.city.lower() == "remote":
            raise ValueError("Give the city, or choose remote.")
        if not self.languages:
            raise ValueError("Pick at least one language.")
        for name in ("apply_by", "starts_on"):
            v = getattr(self, name)
            if v in ("", None):
                setattr(self, name, None)
                continue
            try:
                date.fromisoformat(v)
            except ValueError as e:
                raise ValueError("Dates look like 2026-11-30.") from e
        if self.type == "job":
            self.starts_on, self.duration_weeks, self.batch_every_weeks = None, None, 0
        return self


def _now() -> str:
    return auth.iso(auth.now())


def _row_to_dict(r: sqlite3.Row) -> dict:
    d = dict(r)
    d["data"] = json.loads(d["data"])
    return d


def get(opp_id: str, path: Path | str | None = None) -> dict | None:
    c = connect(path)
    try:
        r = c.execute("SELECT * FROM listings WHERE opp_id = ?", (opp_id,)).fetchone()
        return _row_to_dict(r) if r else None
    finally:
        c.close()


def list_all(status: str | None = None, owner_user_id: int | None = None, path: Path | str | None = None) -> list[dict]:
    q, args = "SELECT * FROM listings WHERE 1=1", []
    if status:
        q += " AND status = ?"; args.append(status)
    if owner_user_id is not None:
        q += " AND owner_user_id = ?"; args.append(owner_user_id)
    c = connect(path)
    try:
        return [_row_to_dict(r) for r in c.execute(q + " ORDER BY created_at, opp_id", args)]
    finally:
        c.close()


def is_managed(opp_id: str) -> bool:
    """Employer posted listings start with E. Sample listings (J, T, M) are managed by the NGO."""
    return opp_id.startswith("E")


def _clean(body: ListingIn, known_names: list[str]) -> dict:
    d = body.model_dump()
    for k in ("title", "org_name", "description", "required_skills_text"):
        d[k] = redact(d[k], known_names)
    return d


def check_dates(body: ListingIn, today: date | None = None) -> None:
    """A new or edited listing cannot close in the past."""
    if body.apply_by and date.fromisoformat(body.apply_by) < (today or date.today()):
        raise ListingError("The last day to apply has already passed. Pick a later date.")


def create(owner_user_id: int, body: ListingIn, submit: bool = False, known_names: list[str] | None = None,
           path: Path | str | None = None, link_owner: bool = True) -> dict:
    """link_owner=False for a listing the NGO posts for itself: it is not added to anyone's "my listings"."""
    check_dates(body)
    data = _clean(body, known_names or [])
    c = connect(path)
    try:
        n = c.execute("SELECT COUNT(*) FROM listings").fetchone()[0]
        opp_id = f"E{n + 1:03d}"
        while c.execute("SELECT 1 FROM listings WHERE opp_id = ?", (opp_id,)).fetchone():
            n += 1
            opp_id = f"E{n + 1:03d}"
        now = _now()
        c.execute("INSERT INTO listings (opp_id, owner_user_id, status, data, openings, created_at, updated_at) VALUES (?,?,?,?,?,?,?)",
                  (opp_id, owner_user_id, "pending" if submit else "draft", json.dumps(data), data["openings"], now, now))
        if link_owner:
            c.execute("INSERT OR IGNORE INTO listing_owners (user_id, opp_id) VALUES (?,?)", (owner_user_id, opp_id))
    finally:
        c.close()
    return get(opp_id, path)  # type: ignore[return-value]


def ngo_edit(opp_id: str, body: ListingIn, known_names: list[str] | None = None, path: Path | str | None = None,
             safety_score: int | None = None) -> dict:
    """An NGO admin edits a listing. The admin is the reviewer, so a live listing stays live. safety_score None keeps it."""
    cur = get(opp_id, path)
    if cur is None:
        raise ListingError("Not found.")
    if safety_score is not None and not 1 <= safety_score <= 5:
        raise ListingError("The safety score is from 1 to 5.")
    check_dates(body)
    data = _clean(body, known_names or [])
    c = connect(path)
    try:
        c.execute("UPDATE listings SET data = ?, openings = ?, safety_score = COALESCE(?, safety_score), updated_at = ? WHERE opp_id = ?",
                  (json.dumps(data), data["openings"], safety_score, _now(), opp_id))
    finally:
        c.close()
    return get(opp_id, path)  # type: ignore[return-value]


def close_expired(today: date | None = None, path: Path | str | None = None) -> list[str]:
    """Close every live listing whose last day to apply has passed. Returns their ids."""
    today = today or date.today()
    gone = [r["opp_id"] for r in list_all("active", path=path)
            if r["data"].get("apply_by") and date.fromisoformat(r["data"]["apply_by"]) < today]
    for oid in gone:
        _set_status(oid, "closed", path, closed_reason="the last day to apply passed")
    return gone


def update(opp_id: str, owner_user_id: int, body: ListingIn, submit: bool = False, known_names: list[str] | None = None,
           path: Path | str | None = None) -> dict:
    cur = get(opp_id, path)
    if cur is None or cur["owner_user_id"] != owner_user_id:
        raise ListingError("Not found.")
    check_dates(body)
    data = _clean(body, known_names or [])
    st = cur["status"]
    if st in ("draft", "rejected"):
        new = "pending" if submit else "draft"
    elif st in ("pending", "active"):
        new = "pending"            # an edit needs a fresh review
    else:
        new = "closed"
    c = connect(path)
    try:
        c.execute("UPDATE listings SET data = ?, openings = ?, status = ?, edited_since_review = ?, updated_at = ? WHERE opp_id = ?",
                  (json.dumps(data), data["openings"], new, 1 if cur["was_approved"] else 0, _now(), opp_id))
    finally:
        c.close()
    return get(opp_id, path)  # type: ignore[return-value]


def _set_status(opp_id: str, status: str, path: Path | str | None = None, **cols) -> None:
    sets = ", ".join(f"{k} = ?" for k in cols)
    c = connect(path)
    try:
        c.execute(f"UPDATE listings SET status = ?, updated_at = ?{', ' + sets if sets else ''} WHERE opp_id = ?",
                  (status, _now(), *cols.values(), opp_id))
    finally:
        c.close()


def submit(opp_id: str, owner_user_id: int, path: Path | str | None = None) -> dict:
    cur = get(opp_id, path)
    if cur is None or cur["owner_user_id"] != owner_user_id:
        raise ListingError("Not found.")
    if cur["status"] not in ("draft", "rejected"):
        raise ListingError("Only a draft or a rejected listing can be submitted.")
    _set_status(opp_id, "pending", path)
    return get(opp_id, path)  # type: ignore[return-value]


def close(opp_id: str, owner_user_id: int | None, reason: str = "closed by the employer", path: Path | str | None = None) -> dict:
    """owner_user_id None means the NGO is closing it."""
    cur = get(opp_id, path)
    if cur is None or (owner_user_id is not None and cur["owner_user_id"] != owner_user_id):
        raise ListingError("Not found.")
    if cur["status"] == "closed":
        raise ListingError("This listing is already closed.")
    _set_status(opp_id, "closed", path, closed_reason=reason)
    return get(opp_id, path)  # type: ignore[return-value]


def reopen(opp_id: str, owner_user_id: int, path: Path | str | None = None) -> dict:
    cur = get(opp_id, path)
    if cur is None or cur["owner_user_id"] != owner_user_id:
        raise ListingError("Not found.")
    if cur["status"] != "closed":
        raise ListingError("Only a closed listing can be reopened.")
    if cur["closed_reason"] == "filled":
        raise ListingError("This listing is filled. Copy it to post it again.")
    if cur["data"].get("apply_by") and date.fromisoformat(cur["data"]["apply_by"]) < date.today():
        raise ListingError("The last day to apply has passed. Edit the listing and pick a new date.")
    back = "active" if cur["was_approved"] and not cur["edited_since_review"] else "pending"
    _set_status(opp_id, back, path, closed_reason=None)
    return get(opp_id, path)  # type: ignore[return-value]


def copy(opp_id: str, owner_user_id: int, known_names: list[str] | None = None, path: Path | str | None = None) -> dict:
    cur = get(opp_id, path)
    if cur is None or cur["owner_user_id"] != owner_user_id:
        raise ListingError("Not found.")
    d = cur["data"]
    d["title"] = (d["title"] + " (copy)")[:80]
    if d.get("apply_by") and date.fromisoformat(d["apply_by"]) < date.today():
        d["apply_by"] = None                       # an old deadline is not copied
    return create(owner_user_id, ListingIn(**d), submit=False, known_names=known_names, path=path)


def review(opp_id: str, reviewer: str, decision: str, safety_score: int, note: str = "", path: Path | str | None = None) -> dict:
    cur = get(opp_id, path)
    if cur is None:
        raise ListingError("Not found.")
    if cur["status"] != "pending":
        raise ListingError("Only a listing that is waiting for review can be reviewed.")
    if decision not in ("approve", "reject"):
        raise ListingError("Choose approve or reject.")
    if not 1 <= safety_score <= 5:
        raise ListingError("The safety score is from 1 to 5.")
    note = (note or "").strip()
    if decision == "reject" and not note:
        raise ListingError("Say why it was rejected, so the employer can fix it.")
    if decision == "approve":
        _set_status(opp_id, "active", path, safety_score=safety_score, review_note=note or None, reviewed_by=reviewer,
                    reviewed_at=_now(), was_approved=1, edited_since_review=0)
    else:
        _set_status(opp_id, "rejected", path, safety_score=safety_score, review_note=note, reviewed_by=reviewer, reviewed_at=_now())
    return get(opp_id, path)  # type: ignore[return-value]


def to_opportunity(row: dict) -> Opportunity:
    """Turn a stored listing into the same Opportunity model the pipeline makes, so matching treats it alike."""
    d = row["data"]
    raw = {"opp_id": row["opp_id"], "type": d["type"], "title": d["title"], "org_name": d["org_name"],
           "job_family": "Mentorship" if d["type"] == "mentor" else "Employer listing", "required_skills_text": d["required_skills_text"], "city": d["city"],
           "mode": d["mode"], "pay_text": d.get("pay_text", ""), "upfront_cost_text": d.get("upfront_cost_text", "0"),
           "hours_per_week": d["hours_per_week"], "night_shift": "yes" if d["night_shift"] else "no",
           "safety_score": row["safety_score"], "languages_required_text": ", ".join(d["languages"]),
           "apply_by": d.get("apply_by") or "", "starts_on": d.get("starts_on") or "",
           "duration_weeks": d.get("duration_weeks") or "", "batch_every_weeks": d.get("batch_every_weeks") or 0}
    opp = clean_opportunity(raw)
    return opp.model_copy(update={"description": d.get("description", ""), "openings": row["openings"]})


def review_flags(row: dict, mapped_skills: int | None = None) -> list[dict]:
    """Things a reviewer should look at before approving. level is red or amber."""
    d, out = row["data"], []
    from .clean import parse_pay, parse_upfront
    cost = parse_upfront(d.get("upfront_cost_text"))
    if d["type"] == "job" and cost > 0:
        out.append({"level": "red", "text": f"Asks for Rs {cost:,} up front. Real employers do not charge a fee to hire."})
    text = " ".join([d["title"], d.get("description", ""), d["required_skills_text"]])
    if PHONE_RE.search(text) or EMAIL_RE.search(text) or CONTACT_WORDS.search(text):
        out.append({"level": "red", "text": "The text asks students to contact someone outside the system, or mentions a fee."})
    if d["night_shift"]:
        out.append({"level": "amber", "text": "Includes night shifts."})
    if d["hours_per_week"] > 54:
        out.append({"level": "amber", "text": f"{d['hours_per_week']} hours a week is long."})
    if d["type"] == "job" and parse_pay(d.get("pay_text"))[0] is None:
        out.append({"level": "amber", "text": "Pay is missing or cannot be read."})
    if mapped_skills == 0:
        out.append({"level": "amber", "text": "None of the skills are in the skill list, so no student can be matched."})
    return out
