"""Append-only audit log. It holds usernames, IDs and codes. Never names, contacts, message text or passwords."""
from __future__ import annotations

import csv
import io
import sqlite3
from pathlib import Path

from .auth import iso, now
from .store import connect


def record(action: str, *, user: dict | sqlite3.Row | None = None, target: str | None = None, ip: str | None = None,
           detail: str | None = None, path: Path | str | None = None, conn: sqlite3.Connection | None = None) -> None:
    own = conn is None
    c = conn or connect(path)
    try:
        u = user or {}
        c.execute("INSERT INTO audit_log (at, user_id, username, role, action, target, ip, detail) VALUES (?,?,?,?,?,?,?,?)",
                  (iso(now()), u["id"] if u and "id" in u.keys() else None, u["username"] if u and "username" in u.keys() else None,
                   u["role"] if u and "role" in u.keys() else None, action, target, ip, detail))
    finally:
        if own:
            c.close()


def list_events(*, action: str | None = None, username: str | None = None, since: str | None = None,
                until: str | None = None, limit: int = 200, path: Path | str | None = None) -> list[dict]:
    q, args = "SELECT * FROM audit_log WHERE 1=1", []
    if action:
        q += " AND action = ?"; args.append(action)
    if username:
        q += " AND username = ?"; args.append(username.lower())
    if since:
        q += " AND at >= ?"; args.append(since)
    if until:
        q += " AND at <= ?"; args.append(until)
    q += " ORDER BY id DESC LIMIT ?"; args.append(max(1, min(limit, 5000)))
    c = connect(path)
    try:
        return [dict(r) for r in c.execute(q, args).fetchall()]
    finally:
        c.close()


def to_csv(events: list[dict]) -> str:
    buf = io.StringIO()
    cols = ["id", "at", "user_id", "username", "role", "action", "target", "ip", "detail"]
    w = csv.writer(buf)
    w.writerow(cols)
    for e in events:
        w.writerow([e.get(k, "") if e.get(k) is not None else "" for k in cols])
    return buf.getvalue()
