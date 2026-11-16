"""Interviews for an application: when, who takes it (the employer or the NGO), how, and the notes afterwards.

This module only stores interviews. meetings.py sends the invites, makes the Meet link and brings the notes back.
Times are stored with their offset (2026-10-20T15:00:00+05:30). A time typed without one is in TIMEZONE.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from . import auth, settings
from .store import connect

MODES = ("meet", "phone", "in_person")
INTERVIEWERS = ("employer", "ngo")
STATUSES = ("scheduled", "done", "cancelled", "no_show")
TAG_RE = re.compile(r"\bINT-(\d+)\b")


class InterviewError(ValueError):
    """The interview cannot be saved like this. The message is safe to show."""


def parse_when(value: str) -> datetime:
    """A start time from the form. Naive times are in the NGO's time zone."""
    try:
        dt = datetime.fromisoformat(value.strip())
    except (ValueError, AttributeError) as e:
        raise InterviewError("Give the date and time, for example 2026-10-20T15:00.") from e
    return dt.replace(tzinfo=ZoneInfo(settings.timezone())) if dt.tzinfo is None else dt


def words(starts_at: str) -> str:
    """"Tue 20 Oct, 3:00 pm" in the NGO's time zone."""
    dt = datetime.fromisoformat(starts_at).astimezone(ZoneInfo(settings.timezone()))
    return f"{dt:%a} {dt.day} {dt:%b}, {int(dt.strftime('%I'))}:{dt:%M} {dt.strftime('%p').lower()}"


def tag(interview_id: int) -> str:
    """Put in the calendar title, so the notetaker's transcript can be matched back to the interview."""
    return f"INT-{interview_id}"


def _now() -> str:
    return auth.iso(auth.now())


def _row(r) -> dict:
    d = dict(r)
    d["action_items"] = json.loads(d["action_items"]) if d.get("action_items") else []
    d["notetaker"] = bool(d["notetaker"])
    d["student_invited"] = bool(d["student_invited"])
    return d


def check(starts_at: str, minutes: int, interviewer: str, *, interviewer_email: str | None = None, mode: str = "meet",
          location: str | None = None, meet_link: str | None = None) -> datetime:
    """Raise InterviewError if this interview cannot be saved; otherwise return its start time. Saves nothing."""
    when = parse_when(starts_at)
    if when < datetime.now(when.tzinfo) - timedelta(minutes=5):
        raise InterviewError("That time has already passed.")
    if not 10 <= minutes <= 240:
        raise InterviewError("An interview is 10 to 240 minutes long.")
    if interviewer not in INTERVIEWERS:
        raise InterviewError("Say who takes the interview: the employer or the NGO.")
    if mode not in MODES:
        raise InterviewError("Choose Google Meet, phone or in person.")
    if meet_link and not re.match(r"^https://[\w.-]+/\S+$", meet_link):
        raise InterviewError("The meeting link must start with https://")
    if interviewer_email and "@" not in interviewer_email:
        raise InterviewError("The interviewer's email does not look right.")
    if mode == "in_person" and not (location or "").strip():
        raise InterviewError("Give the address for an in-person interview.")
    return when


def create(application: dict, starts_at: str, minutes: int, interviewer: str, by: str, *, interviewer_email: str | None = None,
           mode: str = "meet", location: str | None = None, meet_link: str | None = None, notetaker: bool = False,
           path: Path | str | None = None) -> dict:
    when = check(starts_at, minutes, interviewer, interviewer_email=interviewer_email, mode=mode, location=location, meet_link=meet_link)
    now = _now()
    c = connect(path)
    try:
        cur = c.execute(
            "INSERT INTO interviews (application_id, student_id, opp_id, starts_at, minutes, interviewer, interviewer_email, mode,"
            " location, meet_link, notetaker, created_by, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (application["id"], application["student_id"], application["opp_id"], when.isoformat(timespec="minutes"), minutes,
             interviewer, interviewer_email or None, mode, (location or "").strip()[:200] or None, meet_link or None, int(notetaker),
             by, now, now))
        return _row(c.execute("SELECT * FROM interviews WHERE id = ?", (cur.lastrowid,)).fetchone())
    finally:
        c.close()


def get(interview_id: int, path: Path | str | None = None) -> dict | None:
    c = connect(path)
    try:
        r = c.execute("SELECT * FROM interviews WHERE id = ?", (interview_id,)).fetchone()
        return _row(r) if r else None
    finally:
        c.close()


def list_for(*, application_id: int | None = None, student_id: str | None = None, opp_ids: list[str] | None = None,
             upcoming: bool = False, path: Path | str | None = None) -> list[dict]:
    q, args = "SELECT * FROM interviews WHERE 1=1", []
    if application_id is not None:
        q += " AND application_id = ?"; args.append(application_id)
    if student_id:
        q += " AND student_id = ?"; args.append(student_id)
    if opp_ids is not None:
        if not opp_ids:
            return []
        q += f" AND opp_id IN ({','.join('?' * len(opp_ids))})"; args += opp_ids
    c = connect(path)
    try:
        rows = [_row(r) for r in c.execute(q + " ORDER BY starts_at", args)]
    finally:
        c.close()
    if upcoming:
        now = datetime.now().astimezone()
        rows = [r for r in rows if r["status"] == "scheduled" and datetime.fromisoformat(r["starts_at"]) + timedelta(minutes=r["minutes"]) >= now]
    return rows


ALLOWED_UPDATES = {"starts_at", "minutes", "status", "meet_link", "calendar", "calendar_event_id", "location", "interviewer_email",
                   "student_invited", "sequence"}


def update(interview_id: int, path: Path | str | None = None, **fields) -> dict:
    bad = set(fields) - ALLOWED_UPDATES
    if bad:
        raise ValueError(f"cannot update {bad}")
    if "status" in fields and fields["status"] not in STATUSES:
        raise InterviewError("Unknown status.")
    if "starts_at" in fields:
        fields["starts_at"] = parse_when(fields["starts_at"]).isoformat(timespec="minutes")
    if not fields:
        return get(interview_id, path)  # type: ignore[return-value]
    sets = ", ".join(f"{k} = ?" for k in fields)
    c = connect(path)
    try:
        c.execute(f"UPDATE interviews SET {sets}, updated_at = ? WHERE id = ?", (*fields.values(), _now(), interview_id))
    finally:
        c.close()
    return get(interview_id, path)  # type: ignore[return-value]


def set_notes(interview_id: int, summary: str, action_items: list[str], source: str, transcript_id: str | None = None,
              path: Path | str | None = None) -> dict:
    c = connect(path)
    try:
        c.execute("UPDATE interviews SET summary = ?, action_items = ?, notes_source = ?, transcript_id = COALESCE(?, transcript_id),"
                  " status = CASE WHEN status = 'scheduled' THEN 'done' ELSE status END, updated_at = ? WHERE id = ?",
                  ((summary or "")[:3000] or None, json.dumps([a[:300] for a in action_items][:20]), source, transcript_id, _now(), interview_id))
    finally:
        c.close()
    return get(interview_id, path)  # type: ignore[return-value]


def _norm_link(link: str) -> str:
    return re.sub(r"[?#].*$", "", (link or "").strip().lower()).rstrip("/")


def find_by_link(link: str, path: Path | str | None = None) -> dict | None:
    want = _norm_link(link)
    if not want:
        return None
    c = connect(path)
    try:
        rows = [_row(r) for r in c.execute("SELECT * FROM interviews WHERE meet_link IS NOT NULL ORDER BY id DESC")]
    finally:
        c.close()
    return next((r for r in rows if _norm_link(r["meet_link"]) == want), None)


def find_by_tag(title: str, path: Path | str | None = None) -> dict | None:
    m = TAG_RE.search(title or "")
    return get(int(m.group(1)), path) if m else None
