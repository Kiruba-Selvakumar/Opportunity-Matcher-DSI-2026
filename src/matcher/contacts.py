"""The private contact book (data/private/contacts.csv), NGO-approved number changes, and each student's WhatsApp consent.

This is the only module that reads student phones and emails. They are used to send a message and nothing else:
never logged, never shown to employers, never sent to an LLM. WhatsApp messages go only to students who agreed.

A student can ask for a new mobile number. It is used only once NGO staff approve it, so a typo or someone else's
number never receives a student's messages. Approved numbers live in the app database, because the pipeline rewrites
contacts.csv on every run.
"""
from __future__ import annotations

import csv
import re
from pathlib import Path

from . import auth
from .config import PATHS
from .store import connect

_cache: dict = {"key": None, "rows": {}}


def book() -> dict[str, dict]:
    """student_id -> {"name", "phone", "email"}. Reloaded when the file changes."""
    p = Path(PATHS["contacts"])
    if not p.exists():
        return {}
    key = (str(p), p.stat().st_mtime_ns)
    if _cache["key"] != key:
        with p.open(newline="") as f:
            _cache["rows"] = {r["student_id"]: {"name": r.get("name") or "", "phone": r.get("phone") or "", "email": r.get("email") or ""}
                              for r in csv.DictReader(f)}
        _cache["key"] = key
    return _cache["rows"]


def looks_like_sample() -> bool:
    """True when the contact book holds the generated students (their emails are all at example.com)."""
    return any(c["email"].strip().lower().endswith("@example.com") for c in book().values())


def normalize_phone(raw: str | None) -> str | None:
    """An Indian mobile number in the form WhatsApp wants: 91 and ten digits. None when it cannot be one."""
    digits = re.sub(r"\D", "", raw or "")
    if len(digits) == 10 and digits[0] in "6789":
        return "91" + digits
    if len(digits) == 12 and digits.startswith("91") and digits[2] in "6789":
        return digits
    if len(digits) == 11 and digits.startswith("0") and digits[1] in "6789":
        return "91" + digits[1:]
    return None


def phone(student_id: str) -> str | None:
    """The number to use: the latest NGO-approved change, else the one in the contact book."""
    return approved_phones().get(student_id) or normalize_phone(book().get(student_id, {}).get("phone"))


def email(student_id: str) -> str | None:
    e = book().get(student_id, {}).get("email") or ""
    return e if "@" in e else None


def student_by_phone(wa_id: str) -> str | None:
    """Which student a WhatsApp number belongs to, if any."""
    n = normalize_phone(wa_id)
    if not n:
        return None
    approved = approved_phones()
    hit = next((sid for sid, p in approved.items() if p == n), None)
    if hit:
        return hit
    return next((sid for sid, c in book().items() if sid not in approved and normalize_phone(c["phone"]) == n), None)


# ---- number changes, approved by the NGO ----

class ContactError(ValueError):
    pass


def approved_phones(path: Path | str | None = None) -> dict[str, str]:
    """student_id -> the newest approved number."""
    c = connect(path)
    try:
        rows = c.execute("SELECT student_id, phone FROM contact_changes WHERE status = 'approved' ORDER BY id").fetchall()
    finally:
        c.close()
    return {r["student_id"]: r["phone"] for r in rows}


def request_change(student_id: str, raw: str, path: Path | str | None = None) -> dict:
    """Ask for a new number. A new request replaces one still waiting. Nothing changes until staff approve."""
    new = normalize_phone(raw)
    if not new:
        raise ContactError("Enter a 10-digit Indian mobile number, for example 98765 43210.")
    if new == phone(student_id):
        raise ContactError("That is already the number we have for you.")
    taken = student_by_phone(new)
    if taken and taken != student_id:
        raise ContactError("That number belongs to another student. Check it, or message your placement officer.")
    c = connect(path)
    try:
        c.execute("DELETE FROM contact_changes WHERE student_id = ? AND status = 'pending'", (student_id,))
        c.execute("INSERT INTO contact_changes (student_id, phone, requested_at) VALUES (?,?,?)",
                  (student_id, new, auth.iso(auth.now())))
    finally:
        c.close()
    return pending(student_id, path) or {}


def pending(student_id: str, path: Path | str | None = None) -> dict | None:
    c = connect(path)
    try:
        r = c.execute("SELECT * FROM contact_changes WHERE student_id = ? AND status = 'pending' ORDER BY id DESC LIMIT 1",
                      (student_id,)).fetchone()
    finally:
        c.close()
    return dict(r) if r else None


def last_decided(student_id: str, path: Path | str | None = None) -> dict | None:
    c = connect(path)
    try:
        r = c.execute("SELECT * FROM contact_changes WHERE student_id = ? AND status != 'pending' ORDER BY id DESC LIMIT 1",
                      (student_id,)).fetchone()
    finally:
        c.close()
    return dict(r) if r else None


def all_pending(path: Path | str | None = None) -> list[dict]:
    c = connect(path)
    try:
        return [dict(r) for r in c.execute("SELECT * FROM contact_changes WHERE status = 'pending' ORDER BY id")]
    finally:
        c.close()


def decide(change_id: int, approve: bool, by: str, note: str | None = None, path: Path | str | None = None) -> dict:
    """Approve or reject a waiting request. Returns the row; raises ContactError when there is nothing waiting."""
    c = connect(path)
    try:
        r = c.execute("SELECT * FROM contact_changes WHERE id = ?", (change_id,)).fetchone()
        if r is None or r["status"] != "pending":
            raise ContactError("This request was already decided or withdrawn.")
        c.execute("UPDATE contact_changes SET status = ?, decided_by = ?, decided_at = ?, note = ? WHERE id = ?",
                  ("approved" if approve else "rejected", by, auth.iso(auth.now()), (note or "").strip()[:300] or None, change_id))
        return dict(c.execute("SELECT * FROM contact_changes WHERE id = ?", (change_id,)).fetchone())
    finally:
        c.close()


def masked(number: str | None) -> str | None:
    """Only the last four digits, the way a student sees their own number on screen."""
    return f"•••••• {number[-4:]}" if number else None


# ---- consent ----

def set_opt_in(student_id: str, on: bool, by: str, path: Path | str | None = None) -> None:
    c = connect(path)
    try:
        c.execute("INSERT INTO contact_prefs (student_id, whatsapp_opt_in, recorded_by, updated_at) VALUES (?,?,?,?) "
                  "ON CONFLICT(student_id) DO UPDATE SET whatsapp_opt_in = excluded.whatsapp_opt_in, "
                  "recorded_by = excluded.recorded_by, updated_at = excluded.updated_at",
                  (student_id, int(on), by, auth.iso(auth.now())))
    finally:
        c.close()


def opted_in(path: Path | str | None = None) -> set[str]:
    c = connect(path)
    try:
        return {r["student_id"] for r in c.execute("SELECT student_id FROM contact_prefs WHERE whatsapp_opt_in = 1")}
    finally:
        c.close()


def consent(student_id: str, path: Path | str | None = None) -> dict:
    c = connect(path)
    try:
        r = c.execute("SELECT * FROM contact_prefs WHERE student_id = ?", (student_id,)).fetchone()
    finally:
        c.close()
    return {"whatsapp": bool(r and r["whatsapp_opt_in"]), "recorded_by": r["recorded_by"] if r else None,
            "updated_at": r["updated_at"] if r else None, "reachable": phone(student_id) is not None}
