"""The courses and mentors a student picked for their own learning plan. No rows means they use the suggested plan.

Picking a course changes only the plan's preview of what learning it would do. It never changes the student's real
matches: those move when they actually add the skill to their profile.
"""
from __future__ import annotations

from pathlib import Path

from . import auth
from .store import connect

MAX_CHOICES = 6


def get(student_id: str, path: Path | str | None = None) -> list[str] | None:
    """The student's picks in the order they want to take them, or None when they have not picked any (so the suggested plan is shown)."""
    c = connect(path)
    try:
        rows = [r["opp_id"] for r in c.execute("SELECT opp_id FROM plan_choices WHERE student_id = ? ORDER BY position, created_at, opp_id",
                                               (student_id,))]
    finally:
        c.close()
    return rows or None


def save(student_id: str, opp_ids: list[str], path: Path | str | None = None) -> None:
    """Replace the student's picks, keeping their order. An empty list goes back to the suggested plan."""
    ids = list(dict.fromkeys(opp_ids))
    c = connect(path)
    try:
        with c:
            c.execute("DELETE FROM plan_choices WHERE student_id = ?", (student_id,))
            now = auth.iso(auth.now())
            c.executemany("INSERT INTO plan_choices (student_id, opp_id, created_at, position) VALUES (?,?,?,?)",
                          [(student_id, oid, now, i) for i, oid in enumerate(ids)])
    finally:
        c.close()
