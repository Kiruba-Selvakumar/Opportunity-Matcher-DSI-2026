"""One SQLite database for accounts, sessions, decisions, messages and the audit log.

Numbered migrations run in order and are recorded in schema_version, so an upgrade never needs a manual change.
"""
from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

from .config import PATHS

MIGRATIONS: list[tuple[int, str]] = [
    (1, """
        CREATE TABLE IF NOT EXISTS decisions (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          created_at TEXT NOT NULL,
          student_id TEXT NOT NULL,
          opp_id TEXT NOT NULL,
          rank INTEGER,
          final_score REAL,
          decision TEXT NOT NULL CHECK (decision IN ('accept','reject','flag')),
          reject_reason TEXT,
          note TEXT,
          what_if INTEGER NOT NULL DEFAULT 0,
          seconds_to_decide REAL
        );
        CREATE TABLE IF NOT EXISTS messages (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          created_at TEXT NOT NULL,
          thread_type TEXT NOT NULL CHECK (thread_type IN ('student','listing')),
          thread_id TEXT NOT NULL,
          sender_role TEXT NOT NULL CHECK (sender_role IN ('ngo','student','lister')),
          body TEXT NOT NULL,
          about_opp_id TEXT,
          read_by_ngo INTEGER NOT NULL DEFAULT 0,
          read_by_other INTEGER NOT NULL DEFAULT 0
        );
        CREATE INDEX IF NOT EXISTS idx_messages_thread ON messages (thread_type, thread_id, id);
    """),
    (2, """
        CREATE TABLE users (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          username TEXT NOT NULL UNIQUE,
          display_name TEXT NOT NULL,
          password_hash TEXT NOT NULL,
          role TEXT NOT NULL CHECK (role IN ('ngo_admin','ngo_staff','student','employer')),
          student_id TEXT UNIQUE,
          is_active INTEGER NOT NULL DEFAULT 1,
          must_change_password INTEGER NOT NULL DEFAULT 0,
          failed_logins INTEGER NOT NULL DEFAULT 0,
          locked_until TEXT,
          created_at TEXT NOT NULL,
          last_login_at TEXT
        );
        CREATE TABLE listing_owners (
          user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
          opp_id TEXT NOT NULL,
          PRIMARY KEY (user_id, opp_id)
        );
        CREATE TABLE sessions (
          token_hash TEXT PRIMARY KEY,
          user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
          csrf_token TEXT NOT NULL,
          created_at TEXT NOT NULL,
          last_seen_at TEXT NOT NULL,
          expires_at TEXT NOT NULL,
          ip TEXT
        );
        CREATE INDEX idx_sessions_user ON sessions (user_id);
        CREATE TABLE audit_log (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          at TEXT NOT NULL,
          user_id INTEGER,
          username TEXT,
          role TEXT,
          action TEXT NOT NULL,
          target TEXT,
          ip TEXT,
          detail TEXT
        );
        CREATE INDEX idx_audit_at ON audit_log (at);
        CREATE TRIGGER audit_no_update BEFORE UPDATE ON audit_log
          BEGIN SELECT RAISE(ABORT, 'the audit log is append-only'); END;
        CREATE TRIGGER audit_no_delete BEFORE DELETE ON audit_log
          BEGIN SELECT RAISE(ABORT, 'the audit log is append-only'); END;
    """),
    (3, """
        ALTER TABLE decisions ADD COLUMN decided_by TEXT;
        ALTER TABLE messages ADD COLUMN sender_user_id INTEGER;
    """),
    (4, """
        CREATE TABLE listings (
          opp_id TEXT PRIMARY KEY,
          owner_user_id INTEGER NOT NULL REFERENCES users(id),
          status TEXT NOT NULL CHECK (status IN ('draft','pending','active','rejected','closed')),
          data TEXT NOT NULL,
          openings INTEGER NOT NULL DEFAULT 1,
          safety_score INTEGER NOT NULL DEFAULT 3,
          review_note TEXT,
          reviewed_by TEXT,
          reviewed_at TEXT,
          was_approved INTEGER NOT NULL DEFAULT 0,
          edited_since_review INTEGER NOT NULL DEFAULT 0,
          closed_reason TEXT,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL
        );
        CREATE INDEX idx_listings_owner ON listings (owner_user_id);
        CREATE INDEX idx_listings_status ON listings (status);
        CREATE TABLE applications (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          student_id TEXT NOT NULL,
          opp_id TEXT NOT NULL,
          status TEXT NOT NULL,
          student_note TEXT,
          ngo_note TEXT,
          employer_note TEXT,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL,
          status_changed_at TEXT NOT NULL,
          UNIQUE (student_id, opp_id)
        );
        CREATE INDEX idx_applications_opp ON applications (opp_id, status);
        CREATE TABLE application_events (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          application_id INTEGER NOT NULL REFERENCES applications(id) ON DELETE CASCADE,
          at TEXT NOT NULL,
          actor_role TEXT NOT NULL,
          actor_user_id INTEGER,
          from_status TEXT,
          to_status TEXT NOT NULL,
          note TEXT
        );
        CREATE TABLE saved_listings (
          student_id TEXT NOT NULL,
          opp_id TEXT NOT NULL,
          created_at TEXT NOT NULL,
          PRIMARY KEY (student_id, opp_id)
        );
        CREATE TABLE student_edits (
          student_id TEXT PRIMARY KEY,
          data TEXT NOT NULL,
          updated_at TEXT NOT NULL,
          updated_by INTEGER
        );
        CREATE TABLE notifications (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
          kind TEXT NOT NULL,
          text TEXT NOT NULL,
          link TEXT,
          created_at TEXT NOT NULL,
          read_at TEXT
        );
        CREATE INDEX idx_notifications_user ON notifications (user_id, read_at);
        CREATE TABLE student_notes (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          student_id TEXT NOT NULL,
          author TEXT NOT NULL,
          body TEXT NOT NULL,
          follow_up_on TEXT,
          done INTEGER NOT NULL DEFAULT 0,
          created_at TEXT NOT NULL
        );
        CREATE INDEX idx_notes_student ON student_notes (student_id);
    """),
    (5, """
        ALTER TABLE users ADD COLUMN email TEXT;
        ALTER TABLE applications ADD COLUMN recommended_by TEXT;
        ALTER TABLE applications ADD COLUMN recommended_at TEXT;
        CREATE TABLE outbox (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          created_at TEXT NOT NULL,
          channel TEXT NOT NULL CHECK (channel IN ('email','whatsapp')),
          kind TEXT NOT NULL,
          recipient TEXT NOT NULL,
          address TEXT NOT NULL,
          subject TEXT,
          body TEXT NOT NULL,
          status TEXT NOT NULL CHECK (status IN ('queued','sent','delivered','read','failed','dry_run')),
          provider_id TEXT,
          error TEXT,
          batch_id TEXT,
          sent_at TEXT
        );
        CREATE INDEX idx_outbox_at ON outbox (created_at);
        CREATE INDEX idx_outbox_provider ON outbox (provider_id);
        CREATE TABLE contact_prefs (
          student_id TEXT PRIMARY KEY,
          whatsapp_opt_in INTEGER NOT NULL DEFAULT 0,
          recorded_by TEXT,
          updated_at TEXT NOT NULL
        );
        CREATE TABLE resumes (
          student_id TEXT PRIMARY KEY,
          sha256 TEXT NOT NULL,
          bytes INTEGER NOT NULL,
          pages INTEGER NOT NULL,
          source TEXT NOT NULL CHECK (source IN ('student','ngo','bulk')),
          uploaded_by TEXT,
          uploaded_at TEXT NOT NULL,
          quality INTEGER,
          report TEXT
        );
        CREATE TABLE interviews (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          application_id INTEGER NOT NULL REFERENCES applications(id) ON DELETE CASCADE,
          student_id TEXT NOT NULL,
          opp_id TEXT NOT NULL,
          starts_at TEXT NOT NULL,
          minutes INTEGER NOT NULL DEFAULT 30,
          interviewer TEXT NOT NULL CHECK (interviewer IN ('employer','ngo')),
          interviewer_email TEXT,
          mode TEXT NOT NULL DEFAULT 'meet' CHECK (mode IN ('meet','phone','in_person')),
          location TEXT,
          meet_link TEXT,
          calendar TEXT NOT NULL DEFAULT 'none' CHECK (calendar IN ('google','ics','none')),
          calendar_event_id TEXT,
          notetaker INTEGER NOT NULL DEFAULT 0,
          student_invited INTEGER NOT NULL DEFAULT 0,
          sequence INTEGER NOT NULL DEFAULT 0,
          status TEXT NOT NULL DEFAULT 'scheduled' CHECK (status IN ('scheduled','done','cancelled','no_show')),
          transcript_id TEXT,
          summary TEXT,
          action_items TEXT,
          notes_source TEXT,
          created_by TEXT NOT NULL,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL
        );
        CREATE INDEX idx_interviews_start ON interviews (starts_at);
        CREATE INDEX idx_interviews_app ON interviews (application_id);
        CREATE TABLE integrations (
          name TEXT PRIMARY KEY,
          data TEXT NOT NULL,
          updated_by TEXT,
          updated_at TEXT NOT NULL
        );
        CREATE TABLE oauth_states (
          state TEXT PRIMARY KEY,
          user_id INTEGER NOT NULL,
          created_at TEXT NOT NULL
        );
        CREATE TABLE lead_threads (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          channel TEXT NOT NULL DEFAULT 'whatsapp',
          phone TEXT NOT NULL UNIQUE,
          profile_name TEXT,
          status TEXT NOT NULL DEFAULT 'new' CHECK (status IN ('new','mapped','dismissed')),
          mapped_opp_id TEXT,
          mapped_by TEXT,
          note TEXT,
          unread INTEGER NOT NULL DEFAULT 0,
          last_at TEXT NOT NULL,
          created_at TEXT NOT NULL
        );
        CREATE TABLE lead_messages (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          thread_id INTEGER NOT NULL REFERENCES lead_threads(id) ON DELETE CASCADE,
          direction TEXT NOT NULL CHECK (direction IN ('in','out')),
          body TEXT NOT NULL,
          wa_id TEXT UNIQUE,
          at TEXT NOT NULL,
          sent_by TEXT
        );
        CREATE INDEX idx_lead_messages_thread ON lead_messages (thread_id, id);
    """),
    (6, """
        CREATE TABLE contact_changes (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          student_id TEXT NOT NULL,
          phone TEXT NOT NULL,
          requested_at TEXT NOT NULL,
          status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','approved','rejected')),
          decided_by TEXT,
          decided_at TEXT,
          note TEXT
        );
        CREATE INDEX idx_contact_changes_student ON contact_changes (student_id, id);
    """),
    (7, """
        CREATE TABLE plan_choices (
          student_id TEXT NOT NULL,
          opp_id TEXT NOT NULL,
          created_at TEXT NOT NULL,
          PRIMARY KEY (student_id, opp_id)
        );
    """),
    (8, """
        ALTER TABLE plan_choices ADD COLUMN position INTEGER NOT NULL DEFAULT 0;
    """),
]
LATEST = MIGRATIONS[-1][0]


def migrate(conn: sqlite3.Connection) -> int:
    """Apply every migration newer than the database. Returns the version after the run."""
    conn.execute("CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL)")
    row = conn.execute("SELECT MAX(version) FROM schema_version").fetchone()
    current = row[0] or 0
    for version, sql in MIGRATIONS:
        if version > current:
            try:
                conn.executescript("BEGIN;\n" + sql + f"\nINSERT INTO schema_version (version) VALUES ({version});\nCOMMIT;")
            except Exception:
                conn.execute("ROLLBACK") if conn.in_transaction else None
                raise
            current = version
    return current


_migrated: set[str] = set()
_local = threading.local()


class _Kept(sqlite3.Connection):
    """A connection a thread keeps for its whole life. close() does nothing, so every `finally: c.close()` stays right.

    Opening and closing a connection for every query, from many threads at once, can deadlock inside SQLite (3.51 on
    macOS: one thread opening waits in findReusableFd while another closing waits in sqlite3WalClose). Reusing one
    connection per thread means nothing is opened or closed while the app is serving requests.
    """

    def close(self) -> None:
        pass

    def really_close(self) -> None:
        super().close()


def connect(path: Path | str | None = None) -> sqlite3.Connection:
    """This thread's connection to the database, opened (and migrated) the first time."""
    p = Path(path) if path else Path(PATHS["db"])
    key = str(p.resolve())
    kept: dict[str, tuple[_Kept, int]] = _local.__dict__.setdefault("conns", {})
    inode = p.stat().st_ino if p.exists() else None
    hit = kept.get(key)
    if hit and hit[1] == inode:
        return hit[0]
    if hit:                                                    # the file was replaced or removed: start again
        hit[0].really_close()
    p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(p, timeout=10, isolation_level=None, factory=_Kept)  # autocommit: migrations manage their own transactions
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 5000")
    if key not in _migrated or inode is None:
        migrate(conn)
        _migrated.add(key)
    kept[key] = (conn, p.stat().st_ino)
    return conn


def schema_version(path: Path | str | None = None) -> int:
    conn = connect(path)
    try:
        return conn.execute("SELECT MAX(version) FROM schema_version").fetchone()[0] or 0
    finally:
        conn.close()


def backup(dest_dir: Path | str, path: Path | str | None = None) -> Path:
    """Copy the database with SQLite's online backup, which is safe while the app is running."""
    from datetime import datetime
    dest = Path(dest_dir)
    dest.mkdir(parents=True, exist_ok=True)
    out = dest / f"app-{datetime.now().strftime('%Y%m%d-%H%M%S')}.db"
    src = connect(path)
    try:
        dst = sqlite3.connect(out)
        try:
            src.backup(dst)
        finally:
            dst.close()
    finally:
        src.close()
    return out
