"""SQLite decision log. Notes are redacted so staff cannot store phone numbers or emails."""
from __future__ import annotations

import csv
import sqlite3
from datetime import datetime
from pathlib import Path

from .config import PATHS
from .privacy import redact
from .schema import Decision
from .store import connect

COLUMNS = ["id", "created_at", "student_id", "opp_id", "rank", "final_score", "decision", "reject_reason", "note",
           "what_if", "seconds_to_decide", "decided_by"]


def _connect(path: Path | str | None = None) -> sqlite3.Connection:
    return connect(path)


def save_decision(d: Decision, path: Path | str | None = None, known_names: list[str] | None = None,
                  decided_by: str | None = None) -> int:
    d = Decision(**d.model_dump())  # validate again so a mutated object cannot slip through
    note = redact(d.note, known_names or []) if d.note else d.note
    with _connect(path) as conn:
        cur = conn.execute(
            "INSERT INTO decisions (created_at, student_id, opp_id, rank, final_score, decision, reject_reason, note,"
            " what_if, seconds_to_decide, decided_by) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (datetime.now().isoformat(timespec="seconds"), d.student_id, d.opp_id, d.rank, d.final_score,
             d.decision, d.reject_reason, note, int(d.what_if), d.seconds_to_decide, decided_by))
        return int(cur.lastrowid)


def list_decisions(decision: str | None = None, path: Path | str | None = None) -> list[Decision]:
    q = "SELECT * FROM decisions"
    args: tuple = ()
    if decision:
        q += " WHERE decision = ?"
        args = (decision,)
    q += " ORDER BY id DESC"
    conn = _connect(path)
    try:
        rows = conn.execute(q, args).fetchall()
    finally:
        conn.close()
    return [Decision(**{**dict(r), "what_if": bool(r["what_if"])}) for r in rows]


def export_csv(path: Path | str, db_path: Path | str | None = None) -> None:
    rows = list_decisions(path=db_path)
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(COLUMNS)
        for d in rows:
            w.writerow([getattr(d, c) if c != "what_if" else int(d.what_if) for c in COLUMNS])
