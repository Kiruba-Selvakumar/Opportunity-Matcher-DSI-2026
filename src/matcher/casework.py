"""NGO case work: notes with follow-up dates, and one timeline per student."""
from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

from . import applications, auth, chat, db
from .privacy import redact
from .store import connect

MAX_NOTE = 2000
VERB = {"accept": "accepted", "reject": "rejected", "flag": "flagged"}


def add_note(student_id: str, author: str, body: str, follow_up_on: str | None = None,
             known_names: list[str] | None = None, path: Path | str | None = None) -> dict:
    body = redact((body or "").strip(), known_names or [])
    if not body:
        raise ValueError("A note cannot be empty.")
    if len(body) > MAX_NOTE:
        raise ValueError(f"A note can be at most {MAX_NOTE} characters.")
    if follow_up_on:
        try:
            date.fromisoformat(follow_up_on)
        except ValueError as e:
            raise ValueError("The follow-up date must look like 2026-11-30.") from e
    c = connect(path)
    try:
        cur = c.execute("INSERT INTO student_notes (student_id, author, body, follow_up_on, created_at) VALUES (?,?,?,?,?)",
                        (student_id, author, body, follow_up_on or None, auth.iso(auth.now())))
        return dict(c.execute("SELECT * FROM student_notes WHERE id = ?", (cur.lastrowid,)).fetchone())
    finally:
        c.close()


def list_notes(student_id: str, path: Path | str | None = None) -> list[dict]:
    c = connect(path)
    try:
        return [dict(r) for r in c.execute("SELECT * FROM student_notes WHERE student_id = ? ORDER BY id DESC", (student_id,))]
    finally:
        c.close()


def mark_done(note_id: int, path: Path | str | None = None) -> bool:
    c = connect(path)
    try:
        return c.execute("UPDATE student_notes SET done = 1 WHERE id = ?", (note_id,)).rowcount > 0
    finally:
        c.close()


def due_followups(today: str | None = None, path: Path | str | None = None) -> list[dict]:
    today = today or date.today().isoformat()
    c = connect(path)
    try:
        return [dict(r) for r in c.execute("SELECT * FROM student_notes WHERE follow_up_on IS NOT NULL AND done = 0 AND follow_up_on <= ? ORDER BY follow_up_on", (today,))]
    finally:
        c.close()


def _when(ts: str) -> datetime:
    dt = datetime.fromisoformat(ts)
    return dt.astimezone() if dt.tzinfo is None else dt


def timeline(student_id: str, titles: dict[str, str], edited_at: str | None = None, path: Path | str | None = None) -> list[dict]:
    """Everything that happened for one student, newest first. `titles` maps opp_id to a listing title."""
    ev: list[dict] = []
    for d in db.list_decisions(path=path):
        if d.student_id == student_id:
            ev.append({"at": d.created_at, "kind": "decision", "text": f"Staff {VERB[d.decision]} {titles.get(d.opp_id, d.opp_id)}"})
    for a in applications.list_apps(student_id=student_id, path=path):
        for e in applications.events(a["id"], path):
            ev.append({"at": e["at"], "kind": "application", "text": f"{titles.get(a['opp_id'], a['opp_id'])}: {(e['from_status'] or 'new').replace('_', ' ')} to {e['to_status'].replace('_', ' ')} ({e['actor_role']})"})
    for n in list_notes(student_id, path):
        ev.append({"at": n["created_at"], "kind": "note", "text": f"Note by {n['author']}"})
    for m in chat.list_messages("student", student_id, path):
        ev.append({"at": m.created_at or "", "kind": "message", "text": f"{'Staff' if m.sender_role == 'ngo' else 'Student'} wrote: {m.body[:80]}"})
    if edited_at:
        ev.append({"at": edited_at, "kind": "edit", "text": "The student changed their own profile"})
    ev = [e for e in ev if e["at"]]
    ev.sort(key=lambda e: _when(e["at"]), reverse=True)
    return ev
