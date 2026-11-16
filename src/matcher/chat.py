"""Messages between NGO staff and students, and between NGO staff and job listers.

There are no logins in this MVP, so the sender role is chosen by the screen that is open
(staff screens post as ngo, the student view as student, the lister view as lister).
Phones and emails are redacted from every message, like decision notes.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, field_validator, model_validator

from .config import PATHS
from .privacy import redact
from .store import connect

ThreadType = Literal["student", "listing"]
Role = Literal["ngo", "student", "lister"]
ALLOWED = {"student": {"ngo", "student"}, "listing": {"ngo", "lister"}}
MAX_LEN = 2000

class Message(BaseModel):
    id: int | None = None
    created_at: str | None = None
    thread_type: ThreadType
    thread_id: str
    sender_role: Role
    body: str
    about_opp_id: str | None = None
    read_by_ngo: bool = False
    read_by_other: bool = False
    sender_user_id: int | None = None

    @field_validator("body")
    @classmethod
    def body_ok(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("a message cannot be empty")
        if len(v) > MAX_LEN:
            raise ValueError(f"a message can be at most {MAX_LEN} characters")
        return v

    @model_validator(mode="after")
    def role_fits_thread(self):
        if self.sender_role not in ALLOWED[self.thread_type]:
            raise ValueError(f"{self.sender_role} cannot post in a {self.thread_type} thread")
        return self


def _connect(path: Path | str | None = None) -> sqlite3.Connection:
    return connect(path)


def _row(r: sqlite3.Row) -> Message:
    return Message(**{**dict(r), "read_by_ngo": bool(r["read_by_ngo"]), "read_by_other": bool(r["read_by_other"])})


def post_message(m: Message, path: Path | str | None = None, known_names: list[str] | None = None,
                 sender_user_id: int | None = None) -> Message:
    m = Message(**m.model_dump())  # validate again
    body = redact(m.body, known_names or [])
    from_ngo = m.sender_role == "ngo"
    conn = _connect(path)
    try:
        with conn:
            cur = conn.execute(
                "INSERT INTO messages (created_at, thread_type, thread_id, sender_role, body, about_opp_id,"
                " read_by_ngo, read_by_other, sender_user_id) VALUES (?,?,?,?,?,?,?,?,?)",
                (datetime.now().isoformat(timespec="seconds"), m.thread_type, m.thread_id, m.sender_role, body,
                 m.about_opp_id, int(from_ngo), int(not from_ngo), sender_user_id))
            row = conn.execute("SELECT * FROM messages WHERE id = ?", (cur.lastrowid,)).fetchone()
        return _row(row)
    finally:
        conn.close()


def list_messages(thread_type: str, thread_id: str, path: Path | str | None = None) -> list[Message]:
    conn = _connect(path)
    try:
        rows = conn.execute("SELECT * FROM messages WHERE thread_type = ? AND thread_id = ? ORDER BY id",
                            (thread_type, thread_id)).fetchall()
    finally:
        conn.close()
    return [_row(r) for r in rows]


def mark_read(thread_type: str, thread_id: str, reader: Role, path: Path | str | None = None) -> int:
    """Mark the other side's messages as read. Returns how many changed."""
    col, other = ("read_by_ngo", "ngo") if reader == "ngo" else ("read_by_other", None)
    conn = _connect(path)
    try:
        with conn:
            if reader == "ngo":
                cur = conn.execute(f"UPDATE messages SET {col} = 1 WHERE thread_type = ? AND thread_id = ? "
                                   f"AND sender_role != 'ngo' AND {col} = 0", (thread_type, thread_id))
            else:
                cur = conn.execute(f"UPDATE messages SET {col} = 1 WHERE thread_type = ? AND thread_id = ? "
                                   f"AND sender_role = 'ngo' AND {col} = 0", (thread_type, thread_id))
        return cur.rowcount
    finally:
        conn.close()


def unread_from_ngo(thread_type: str, thread_id: str, path: Path | str | None = None) -> int:
    """How many NGO messages in this thread the student or employer has not opened yet."""
    conn = _connect(path)
    try:
        return conn.execute("SELECT COUNT(*) FROM messages WHERE thread_type = ? AND thread_id = ? AND sender_role = 'ngo' "
                            "AND read_by_other = 0", (thread_type, thread_id)).fetchone()[0]
    finally:
        conn.close()


def list_threads(path: Path | str | None = None) -> list[dict]:
    """One row per thread for the NGO inbox: last message, message count and unread count, newest first."""
    conn = _connect(path)
    try:
        rows = conn.execute("""
            SELECT thread_type, thread_id, COUNT(*) AS n,
                   SUM(CASE WHEN sender_role != 'ngo' AND read_by_ngo = 0 THEN 1 ELSE 0 END) AS unread,
                   MAX(id) AS last_id
            FROM messages GROUP BY thread_type, thread_id ORDER BY last_id DESC""").fetchall()
        out = []
        for r in rows:
            last = conn.execute("SELECT * FROM messages WHERE id = ?", (r["last_id"],)).fetchone()
            out.append({"thread_type": r["thread_type"], "thread_id": r["thread_id"], "count": r["n"],
                        "unread": r["unread"] or 0, "last_body": last["body"], "last_role": last["sender_role"],
                        "last_at": last["created_at"]})
        return out
    finally:
        conn.close()


def unread_total(path: Path | str | None = None) -> int:
    return sum(t["unread"] for t in list_threads(path))
