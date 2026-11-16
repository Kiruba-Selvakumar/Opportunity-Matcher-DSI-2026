import sqlite3

import pytest

from matcher import store


def test_migrations_on_empty_db(tmp_path):
    p = tmp_path / "a.db"
    assert store.schema_version(p) == store.LATEST
    c = store.connect(p)
    tables = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"users", "sessions", "listing_owners", "audit_log", "decisions", "messages", "schema_version"} <= tables
    assert c.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    assert c.execute("PRAGMA journal_mode").fetchone()[0] == "wal"


def test_upgrade_from_a_database_at_version_1(tmp_path):
    p = tmp_path / "old.db"
    raw = sqlite3.connect(p, isolation_level=None)
    raw.execute("CREATE TABLE schema_version (version INTEGER NOT NULL)")
    raw.executescript(store.MIGRATIONS[0][1] + "INSERT INTO schema_version VALUES (1);")
    raw.execute("INSERT INTO decisions (created_at, student_id, opp_id, decision) VALUES ('t','S1','J1','accept')")
    raw.close()
    assert store.schema_version(p) == store.LATEST
    c = store.connect(p)
    assert c.execute("SELECT student_id, decided_by FROM decisions").fetchone()["student_id"] == "S1"  # data kept


def test_connecting_twice_does_not_repeat_migrations(tmp_path):
    p = tmp_path / "a.db"
    store.connect(p).close()
    store.connect(p).close()
    c = store.connect(p)
    assert c.execute("SELECT COUNT(*) FROM schema_version").fetchone()[0] == store.LATEST


def test_audit_log_is_append_only(tmp_path):
    c = store.connect(tmp_path / "a.db")
    c.execute("INSERT INTO audit_log (at, action) VALUES ('t','x')")
    with pytest.raises(sqlite3.DatabaseError, match="append-only"):
        c.execute("UPDATE audit_log SET action = 'y'")
    with pytest.raises(sqlite3.DatabaseError, match="append-only"):
        c.execute("DELETE FROM audit_log")


def test_backup_is_readable(tmp_path):
    p = tmp_path / "a.db"
    c = store.connect(p)
    c.execute("INSERT INTO audit_log (at, action) VALUES ('t','kept')")
    out = store.backup(tmp_path / "bk", p)
    copy = sqlite3.connect(out)
    assert copy.execute("SELECT action FROM audit_log").fetchone()[0] == "kept"


def test_each_thread_keeps_one_connection(tmp_path):
    """Opening and closing a connection per query from many threads can deadlock inside SQLite, so threads reuse one."""
    import threading
    p = tmp_path / "a.db"
    a = store.connect(p)
    a.close()                                                    # a no-op: the connection stays usable
    assert store.connect(p) is a and a.execute("SELECT 1").fetchone()[0] == 1
    other = []
    t = threading.Thread(target=lambda: other.append(store.connect(p)))
    t.start(); t.join()
    assert other[0] is not a                                     # another thread gets its own


def test_a_removed_database_is_made_again(tmp_path):
    p = tmp_path / "a.db"
    store.connect(p).execute("INSERT INTO audit_log (at, action) VALUES ('t','x')")
    for suffix in ("", "-wal", "-shm"):
        f = tmp_path / f"a.db{suffix}"
        if f.exists():
            f.unlink()
    c = store.connect(p)
    assert c.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0] == 0
    assert c.execute("SELECT MAX(version) FROM schema_version").fetchone()[0] == store.LATEST
