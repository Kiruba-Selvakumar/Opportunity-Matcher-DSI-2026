"""In-app notifications. The text never holds names, phone numbers, emails or message text."""
from __future__ import annotations

from pathlib import Path

from . import auth
from .store import connect


def add(user_ids: list[int] | int, kind: str, text: str, link: str | None = None, path: Path | str | None = None) -> int:
    ids = [user_ids] if isinstance(user_ids, int) else list(dict.fromkeys(user_ids))
    if not ids:
        return 0
    c = connect(path)
    try:
        now = auth.iso(auth.now())
        for uid in ids:
            c.execute("INSERT INTO notifications (user_id, kind, text, link, created_at) VALUES (?,?,?,?,?)", (uid, kind, text[:200], link, now))
        return len(ids)
    finally:
        c.close()


def list_for(user_id: int, limit: int = 50, path: Path | str | None = None) -> list[dict]:
    c = connect(path)
    try:
        return [dict(r) for r in c.execute("SELECT * FROM notifications WHERE user_id = ? ORDER BY id DESC LIMIT ?", (user_id, limit))]
    finally:
        c.close()


def unread(user_id: int, path: Path | str | None = None) -> int:
    c = connect(path)
    try:
        return c.execute("SELECT COUNT(*) FROM notifications WHERE user_id = ? AND read_at IS NULL", (user_id,)).fetchone()[0]
    finally:
        c.close()


def mark_read(user_id: int, notification_id: int, path: Path | str | None = None) -> bool:
    c = connect(path)
    try:
        return c.execute("UPDATE notifications SET read_at = ? WHERE id = ? AND user_id = ? AND read_at IS NULL",
                         (auth.iso(auth.now()), notification_id, user_id)).rowcount > 0
    finally:
        c.close()


def mark_all(user_id: int, path: Path | str | None = None) -> int:
    c = connect(path)
    try:
        return c.execute("UPDATE notifications SET read_at = ? WHERE user_id = ? AND read_at IS NULL", (auth.iso(auth.now()), user_id)).rowcount
    finally:
        c.close()


# ---- who to tell ----

def ngo_user_ids(path: Path | str | None = None) -> list[int]:
    c = connect(path)
    try:
        return [r["id"] for r in c.execute("SELECT id FROM users WHERE role IN ('ngo_admin','ngo_staff') AND is_active = 1")]
    finally:
        c.close()


def admin_user_ids(path: Path | str | None = None) -> list[int]:
    """NGO admins only: they approve listings and share students, so their queue is theirs."""
    c = connect(path)
    try:
        return [r["id"] for r in c.execute("SELECT id FROM users WHERE role = 'ngo_admin' AND is_active = 1")]
    finally:
        c.close()


def owner_user_ids(opp_id: str, path: Path | str | None = None) -> list[int]:
    c = connect(path)
    try:
        return [r["user_id"] for r in c.execute("SELECT lo.user_id FROM listing_owners lo JOIN users u ON u.id = lo.user_id WHERE lo.opp_id = ? AND u.is_active = 1", (opp_id,))]
    finally:
        c.close()


def student_user_id(student_id: str, path: Path | str | None = None) -> int | None:
    c = connect(path)
    try:
        r = c.execute("SELECT id FROM users WHERE student_id = ? AND is_active = 1", (student_id,)).fetchone()
        return r["id"] if r else None
    finally:
        c.close()
