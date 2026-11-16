"""Every email and WhatsApp message the app sends, and what happened to it.

A message is written here first and then sent, so a failed send is never lost. Without SMTP or WhatsApp settings the row
is a dry run: the app behaves the same and staff can read what would have gone out. Student phones and emails are stored
masked. Sending runs on a small background pool, or inside the request when OUTBOX_SYNC=1 (tests).
"""
from __future__ import annotations

import re
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Callable

from . import auth, settings
from .store import connect

_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="outbox")
ORDER = {"queued": 0, "dry_run": 0, "sent": 1, "delivered": 2, "read": 3}


def mask(address: str) -> str:
    """ravi@x.com -> r***@x.com, 919876543210 -> ********3210."""
    if "@" in address:
        user, domain = address.split("@", 1)
        return f"{user[:1]}***@{domain}"
    digits = re.sub(r"\D", "", address)
    return "*" * max(0, len(digits) - 4) + digits[-4:]


def new_batch() -> str:
    return uuid.uuid4().hex[:10]


def run(fn: Callable[[], None]) -> None:
    if settings.sync_delivery():
        fn()
    else:
        _pool.submit(fn)


def add(channel: str, kind: str, recipient: str, address: str, body: str, subject: str | None = None,
        status: str = "queued", batch_id: str | None = None, path: Path | str | None = None) -> int:
    c = connect(path)
    try:
        cur = c.execute("INSERT INTO outbox (created_at, channel, kind, recipient, address, subject, body, status, batch_id)"
                        " VALUES (?,?,?,?,?,?,?,?,?)",
                        (auth.iso(auth.now()), channel, kind, recipient, address, subject, body[:4000], status, batch_id))
        return int(cur.lastrowid)  # type: ignore[arg-type]
    finally:
        c.close()


def mark(outbox_id: int, status: str, provider_id: str | None = None, error: str | None = None,
         path: Path | str | None = None) -> None:
    c = connect(path)
    try:
        c.execute("UPDATE outbox SET status = ?, provider_id = COALESCE(?, provider_id), error = ?, sent_at = ? WHERE id = ?",
                  (status, provider_id, (error or None) and error[:300], auth.iso(auth.now()) if status == "sent" else None, outbox_id))
    finally:
        c.close()


def update_by_provider_id(provider_id: str, status: str, error: str | None = None, path: Path | str | None = None) -> bool:
    """A delivery report from the provider. Statuses only move forward (sent, delivered, read); failed always wins."""
    c = connect(path)
    try:
        row = c.execute("SELECT id, status FROM outbox WHERE provider_id = ?", (provider_id,)).fetchone()
        if row is None:
            return False
        if status != "failed" and ORDER.get(status, -1) <= ORDER.get(row["status"], -1):
            return False
        c.execute("UPDATE outbox SET status = ?, error = COALESCE(?, error) WHERE id = ?", (status, error, row["id"]))
        return True
    finally:
        c.close()


def list_items(channel: str | None = None, batch_id: str | None = None, limit: int = 200,
               path: Path | str | None = None) -> list[dict]:
    q, args = "SELECT * FROM outbox WHERE 1=1", []
    if channel:
        q += " AND channel = ?"; args.append(channel)
    if batch_id:
        q += " AND batch_id = ?"; args.append(batch_id)
    c = connect(path)
    try:
        return [dict(r) for r in c.execute(q + " ORDER BY id DESC LIMIT ?", (*args, min(max(limit, 1), 1000)))]
    finally:
        c.close()


def batch_counts(batch_id: str, path: Path | str | None = None) -> dict[str, int]:
    c = connect(path)
    try:
        return {r["status"]: r["n"] for r in c.execute("SELECT status, COUNT(*) n FROM outbox WHERE batch_id = ? GROUP BY status", (batch_id,))}
    finally:
        c.close()
