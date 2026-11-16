"""A student's interest in a listing, and its journey: interested, shared, shortlisted, interview, offered, hired."""
from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

from . import auth
from .privacy import redact
from .store import connect

STATUSES = ("interested", "shared", "shortlisted", "interview", "offered", "hired", "declined", "not_a_fit", "withdrawn")
ACTIVE = ("interested", "shared", "shortlisted", "interview", "offered")
EMPLOYER_STAGES = ("shared", "shortlisted", "interview", "offered", "hired")
NEXT = {"shared": ("shortlisted",), "shortlisted": ("interview",), "interview": ("offered",), "offered": ("hired",)}

WORDS = {  # plain sentences for the student
    "interested": "You asked about this. The NGO will look at it next.",
    "shared": "The NGO shared your profile with the employer. You do not need to do anything.",
    "shortlisted": "The employer put you on their shortlist.",
    "interview": "The employer wants to interview you. The NGO will contact you with the details.",
    "offered": "The employer is making you an offer. The NGO will talk to you about it.",
    "hired": "You got the job.",
    "declined": "The NGO decided not to share this one yet. See the note for why.",
    "not_a_fit": "The employer decided this was not the right fit. See the note.",
    "withdrawn": "You stepped back from this one.",
}


class ApplicationError(ValueError):
    """The change is not allowed. The message is safe to show."""


def allowed(role: str, frm: str | None, to: str) -> bool:
    if role == "student":
        return (frm is None and to == "interested") or (frm in ACTIVE and to == "withdrawn")
    if role == "ngo":
        if frm == "interested":
            return to in ("shared", "declined")
        return frm in ACTIVE and to in EMPLOYER_STAGES + ("not_a_fit",) and to != frm
    if role == "lister":
        return frm in NEXT and (to in NEXT[frm] or to == "not_a_fit")
    return False


def _now() -> str:
    return auth.iso(auth.now())


def _row(r: sqlite3.Row) -> dict:
    d = dict(r)
    d["days_in_stage"] = max(0, (auth.now() - auth.parse(d["status_changed_at"])).days)
    d["words"] = WORDS.get(d["status"], "")
    return d


def get(app_id: int, path: Path | str | None = None) -> dict | None:
    c = connect(path)
    try:
        r = c.execute("SELECT * FROM applications WHERE id = ?", (app_id,)).fetchone()
        return _row(r) if r else None
    finally:
        c.close()


def find(student_id: str, opp_id: str, path: Path | str | None = None) -> dict | None:
    c = connect(path)
    try:
        r = c.execute("SELECT * FROM applications WHERE student_id = ? AND opp_id = ?", (student_id, opp_id)).fetchone()
        return _row(r) if r else None
    finally:
        c.close()


def _event(c: sqlite3.Connection, app_id: int, role: str, user_id: int | None, frm: str | None, to: str, note: str | None) -> None:
    c.execute("INSERT INTO application_events (application_id, at, actor_role, actor_user_id, from_status, to_status, note) VALUES (?,?,?,?,?,?,?)",
              (app_id, _now(), role, user_id, frm, to, note))


def create(student_id: str, opp_id: str, note: str = "", user_id: int | None = None, known_names: list[str] | None = None,
           path: Path | str | None = None) -> dict:
    note = redact((note or "").strip()[:500], known_names or [])
    c = connect(path)
    try:
        old = c.execute("SELECT * FROM applications WHERE student_id = ? AND opp_id = ?", (student_id, opp_id)).fetchone()
        now = _now()
        if old is not None:
            if old["status"] in ACTIVE:
                raise ApplicationError("You have already shown interest in this.")
            if old["status"] in ("declined", "not_a_fit"):
                raise ApplicationError("This one was closed, so it cannot be opened again.")
            # withdrawn: allowed to come back
            c.execute("UPDATE applications SET status = 'interested', student_note = ?, updated_at = ?, status_changed_at = ? WHERE id = ?",
                      (note or None, now, now, old["id"]))
            _event(c, old["id"], "student", user_id, "withdrawn", "interested", note or None)
            app_id = old["id"]
        else:
            cur = c.execute("INSERT INTO applications (student_id, opp_id, status, student_note, created_at, updated_at, status_changed_at)"
                            " VALUES (?,?,?,?,?,?,?)", (student_id, opp_id, "interested", note or None, now, now, now))
            app_id = cur.lastrowid
            _event(c, app_id, "student", user_id, None, "interested", note or None)
        c.execute("DELETE FROM saved_listings WHERE student_id = ? AND opp_id = ?", (student_id, opp_id))
    finally:
        c.close()
    return get(app_id, path)  # type: ignore[arg-type]


def transition(app_id: int, to: str, role: str, user_id: int | None = None, note: str = "",
               known_names: list[str] | None = None, path: Path | str | None = None) -> dict:
    cur = get(app_id, path)
    if cur is None:
        raise ApplicationError("Not found.")
    if to not in STATUSES or not allowed(role, cur["status"], to):
        raise ApplicationError(f"This cannot be moved from {cur['status'].replace('_', ' ')} to {to.replace('_', ' ')}.")
    note = redact((note or "").strip()[:500], known_names or [])
    if to in ("declined", "not_a_fit") and not note:
        raise ApplicationError("Add a short reason, so the student understands.")
    col = {"student": "student_note", "ngo": "ngo_note", "lister": "employer_note"}[role]
    now = _now()
    c = connect(path)
    try:
        c.execute(f"UPDATE applications SET status = ?, {col} = COALESCE(?, {col}), updated_at = ?, status_changed_at = ? WHERE id = ?",
                  (to, note or None, now, now, app_id))
        _event(c, app_id, role, user_id, cur["status"], to, note or None)
    finally:
        c.close()
    return get(app_id, path)  # type: ignore[return-value]


def recommend(app_id: int, by: str, note: str = "", known_names: list[str] | None = None, path: Path | str | None = None) -> dict:
    """NGO staff put an interested student forward. Only an NGO admin shares them with the employer (the admin is the gate)."""
    cur = get(app_id, path)
    if cur is None:
        raise ApplicationError("Not found.")
    if cur["status"] != "interested":
        raise ApplicationError("Only a student who is waiting to be shared can be put forward.")
    note = redact((note or "").strip()[:500], known_names or [])
    c = connect(path)
    try:
        c.execute("UPDATE applications SET recommended_by = ?, recommended_at = ?, ngo_note = COALESCE(?, ngo_note), updated_at = ? WHERE id = ?",
                  (by, _now(), note or None, _now(), app_id))
    finally:
        c.close()
    return get(app_id, path)  # type: ignore[return-value]


def events(app_id: int, path: Path | str | None = None) -> list[dict]:
    c = connect(path)
    try:
        return [dict(r) for r in c.execute("SELECT at, actor_role, from_status, to_status, note FROM application_events WHERE application_id = ? ORDER BY id", (app_id,))]
    finally:
        c.close()


def list_apps(status: str | None = None, student_id: str | None = None, opp_id: str | None = None,
              statuses: tuple[str, ...] | None = None, path: Path | str | None = None) -> list[dict]:
    q, args = "SELECT * FROM applications WHERE 1=1", []
    if status:
        q += " AND status = ?"; args.append(status)
    if statuses:
        q += f" AND status IN ({','.join('?' * len(statuses))})"; args += list(statuses)
    if student_id:
        q += " AND student_id = ?"; args.append(student_id)
    if opp_id:
        q += " AND opp_id = ?"; args.append(opp_id)
    c = connect(path)
    try:
        return [_row(r) for r in c.execute(q + " ORDER BY updated_at DESC, id DESC", args)]
    finally:
        c.close()


def load_by_listing(path: Path | str | None = None) -> dict[str, int]:
    """How many students are in play for each listing. Used to spread students out (matching v2)."""
    c = connect(path)
    try:
        q = f"SELECT opp_id, COUNT(*) n FROM applications WHERE status IN ({','.join('?' * len(ACTIVE))}) GROUP BY opp_id"
        return {r["opp_id"]: r["n"] for r in c.execute(q, ACTIVE)}
    finally:
        c.close()


def hired_count(opp_id: str, path: Path | str | None = None) -> int:
    c = connect(path)
    try:
        return c.execute("SELECT COUNT(*) FROM applications WHERE opp_id = ? AND status = 'hired'", (opp_id,)).fetchone()[0]
    finally:
        c.close()


def funnel(path: Path | str | None = None) -> dict[str, int]:
    """Students who reached each stage at least once, from the event history."""
    c = connect(path)
    try:
        out = {}
        for st in ("interested", "shared", "shortlisted", "interview", "offered", "hired"):
            out[st] = c.execute("SELECT COUNT(DISTINCT application_id) FROM application_events WHERE to_status = ?", (st,)).fetchone()[0]
        return out
    finally:
        c.close()


# ---- saved listings ----

def save(student_id: str, opp_id: str, path: Path | str | None = None) -> None:
    c = connect(path)
    try:
        c.execute("INSERT OR IGNORE INTO saved_listings (student_id, opp_id, created_at) VALUES (?,?,?)", (student_id, opp_id, _now()))
    finally:
        c.close()


def unsave(student_id: str, opp_id: str, path: Path | str | None = None) -> None:
    c = connect(path)
    try:
        c.execute("DELETE FROM saved_listings WHERE student_id = ? AND opp_id = ?", (student_id, opp_id))
    finally:
        c.close()


def saved(student_id: str, path: Path | str | None = None) -> list[str]:
    c = connect(path)
    try:
        return [r["opp_id"] for r in c.execute("SELECT opp_id FROM saved_listings WHERE student_id = ? ORDER BY created_at DESC", (student_id,))]
    finally:
        c.close()


def shared_ids(opp_id: str, path: Path | str | None = None) -> set[int]:
    """Applications the NGO has passed to the employer at least once. Only these are visible to the employer."""
    c = connect(path)
    try:
        return {r["application_id"] for r in c.execute(
            "SELECT DISTINCT e.application_id FROM application_events e JOIN applications a ON a.id = e.application_id "
            "WHERE a.opp_id = ? AND e.to_status = 'shared'", (opp_id,))}
    finally:
        c.close()
