"""Employer leads: people who write to the NGO's WhatsApp number about a job or a training.

Each sender gets one conversation. The NGO admin reads it, replies, and maps it: turns it into a listing (pre-filled from
the text by suggest_listing) or dismisses it. A lead's number is an employer contact, so it is kept for replies, but it
is only ever shown to NGO admins.
"""
from __future__ import annotations

import re
import sqlite3
from pathlib import Path

from . import auth
from .clean import parse_pay
from .store import connect

CITIES = ["Hyderabad", "Bengaluru", "Bangalore", "Chennai", "Pune", "Warangal", "Visakhapatnam", "Vizag", "Vijayawada",
          "Guntur", "Tirupati", "Khammam", "Karimnagar", "Nizamabad", "Nalgonda", "Mahabubnagar"]
CITY_NAME = {"Bangalore": "Bengaluru", "Vizag": "Visakhapatnam"}
STATUSES = ("new", "mapped", "dismissed")
FILLER = {"freshers", "fresher", "candidates", "people", "students", "someone", "staff", "graduates"}
ACRONYMS = {"qa", "it", "ml", "ai", "sql", "ui", "ux", "hr", "bpo", "soc", "aws", "iot"}


def _now() -> str:
    return auth.iso(auth.now())


def record_incoming(phone: str, text: str, wa_id: str, profile_name: str | None = None, path: Path | str | None = None) -> int | None:
    """Add one incoming message. Returns the thread id, or None when this message was already stored (Meta retries)."""
    c = connect(path)
    try:
        now = _now()
        row = c.execute("SELECT id, status FROM lead_threads WHERE phone = ?", (phone,)).fetchone()
        if row is None:
            tid = c.execute("INSERT INTO lead_threads (phone, profile_name, last_at, created_at) VALUES (?,?,?,?)",
                            (phone, (profile_name or "")[:80] or None, now, now)).lastrowid
        else:
            tid = row["id"]
        try:
            c.execute("INSERT INTO lead_messages (thread_id, direction, body, wa_id, at) VALUES (?,?,?,?,?)",
                      (tid, "in", text[:4000], wa_id or None, now))
        except sqlite3.IntegrityError:
            return None
        c.execute("UPDATE lead_threads SET unread = unread + 1, last_at = ?, profile_name = COALESCE(profile_name, ?), "
                  "status = CASE WHEN status = 'dismissed' THEN 'new' ELSE status END WHERE id = ?",
                  (now, (profile_name or "")[:80] or None, tid))
        return int(tid)  # type: ignore[arg-type]
    finally:
        c.close()


AUTO_REPLY = ("Thank you for writing to the NGO. To list your opening, please send the job title, skills needed, city or remote, pay, "
              "number of openings and last day to apply. Our team will check it and reply here.")


def is_first_message(thread_id: int, path: Path | str | None = None) -> bool:
    c = connect(path)
    try:
        return c.execute("SELECT COUNT(*) FROM lead_messages WHERE thread_id = ?", (thread_id,)).fetchone()[0] == 1
    finally:
        c.close()


def record_outgoing(thread_id: int, text: str, by: str, path: Path | str | None = None) -> None:
    c = connect(path)
    try:
        c.execute("INSERT INTO lead_messages (thread_id, direction, body, at, sent_by) VALUES (?,?,?,?,?)",
                  (thread_id, "out", text[:4000], _now(), by))
        c.execute("UPDATE lead_threads SET last_at = ? WHERE id = ?", (_now(), thread_id))
    finally:
        c.close()


def list_threads(status: str | None = None, path: Path | str | None = None) -> list[dict]:
    q, args = ("SELECT t.*, (SELECT body FROM lead_messages m WHERE m.thread_id = t.id AND m.direction = 'in' ORDER BY m.id DESC LIMIT 1) AS last_body, "
               "(SELECT COUNT(*) FROM lead_messages m WHERE m.thread_id = t.id) AS count FROM lead_threads t WHERE 1=1"), []
    if status:
        q += " AND t.status = ?"; args.append(status)
    c = connect(path)
    try:
        return [dict(r) for r in c.execute(q + " ORDER BY t.last_at DESC, t.id DESC", args)]
    finally:
        c.close()


def get_thread(thread_id: int, path: Path | str | None = None) -> dict | None:
    c = connect(path)
    try:
        r = c.execute("SELECT * FROM lead_threads WHERE id = ?", (thread_id,)).fetchone()
        if r is None:
            return None
        msgs = [dict(m) for m in c.execute("SELECT id, direction, body, at, sent_by FROM lead_messages WHERE thread_id = ? ORDER BY id", (thread_id,))]
        c.execute("UPDATE lead_threads SET unread = 0 WHERE id = ?", (thread_id,))
        return {**dict(r), "messages": msgs}
    finally:
        c.close()


def set_status(thread_id: int, status: str, by: str, mapped_opp_id: str | None = None, note: str | None = None,
               path: Path | str | None = None) -> bool:
    if status not in STATUSES:
        raise ValueError("Unknown status.")
    c = connect(path)
    try:
        return c.execute("UPDATE lead_threads SET status = ?, mapped_opp_id = COALESCE(?, mapped_opp_id), mapped_by = ?, note = COALESCE(?, note) WHERE id = ?",
                         (status, mapped_opp_id, by, note, thread_id)).rowcount > 0
    finally:
        c.close()


def unread_total(path: Path | str | None = None) -> int:
    c = connect(path)
    try:
        return c.execute("SELECT COALESCE(SUM(unread), 0) FROM lead_threads WHERE status != 'dismissed'").fetchone()[0]
    finally:
        c.close()


# ---- turning a conversation into a listing ----

def suggest_listing(text: str, profile_name: str | None = None) -> dict:
    """A listing form pre-filled from what the employer wrote. Rules only, so nothing leaves the machine. Staff check it."""
    from .parse_text import _found, _skill_terms
    t = text or ""
    low = t.lower()
    skills: list[str] = []
    for term, canon in _skill_terms():
        if canon not in skills and _found(t, term):
            skills.append(canon)
    city = next((CITY_NAME.get(c, c) for c in CITIES if re.search(rf"\b{c}\b", t, re.I)), "")
    remote = bool(re.search(r"\b(remote|work from home|wfh)\b", low))
    kind = "training" if re.search(r"\b(training|course|batch|bootcamp|workshop)\b", low) else "job"
    m = re.search(r"(\d+)\s+(?:[a-z]+\s+){0,3}?(?:openings?|positions?|vacanc(?:y|ies)|freshers|candidates|people|trainees|interns|"
                  r"engineers|developers|testers|analysts|associates)\b", low)
    openings = min(50, max(1, int(m.group(1)))) if m else 1
    pay = ""
    pm = re.search(r"(\d+(?:\.\d+)?\s*(?:-|to)?\s*\d*(?:\.\d+)?\s*lpa)|((?:rs\.?|₹)\s*[\d,]+(?:\s*(?:k))?\s*(?:per|/|a)\s*month)|(stipend[^.,\n]{0,25})", low)
    if pm and parse_pay(pm.group(0))[0] is not None:
        pay = pm.group(0).strip()
    hours = 40
    hm = re.search(r"(\d{2})\s*(?:hours|hrs)\s*(?:a|per|/)\s*week", low)
    if hm:
        hours = min(80, max(1, int(hm.group(1))))
    title = ""
    tm = (re.search(r"(?:for|as)\s+(?:an?\s+|the\s+)?([a-z][a-z /&+.-]{2,40}?)\s+(?:role|position|post|job|opening)s?\b", low)
          or re.search(r"(?:hiring|need|looking for|require|requirement for|opening for)\s+(?:an?\s+|\d+\s+)?([a-z][a-z /&+.-]{2,50}?)(?:\s+(?:in|at|for|with|who)\b|[.,\n]|$)", low))
    if tm and tm.group(1).strip() not in FILLER:
        title = " ".join(w.upper() if w in ACRONYMS else w.capitalize() for w in tm.group(1).strip(" .-").split())
    if not title and skills:
        title = f"{skills[0]} {'Trainee' if kind == 'job' else 'Course'}"
    langs = [lang for lang in ("English", "Telugu", "Hindi") if lang.lower() in low] or ["English"]
    night = bool(re.search(r"\bnight shifts?\b", low))
    return {"title": title[:80] or "New opening", "type": kind, "org_name": (profile_name or "")[:80], "description": t.strip()[:1000],
            "required_skills_text": ", ".join(skills)[:300], "city": "" if remote else city, "mode": "remote" if remote else "onsite",
            "pay_text": pay[:60], "upfront_cost_text": "0", "hours_per_week": hours, "night_shift": night,
            "languages": langs, "openings": openings,
            "found": {"skills": skills, "city": city or None, "pay": pay or None, "openings": bool(m)}}
