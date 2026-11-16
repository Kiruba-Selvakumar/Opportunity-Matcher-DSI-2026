"""User accounts: create, sign in, change passwords, list owners. Also the command line (create-admin, seed-demo, backup)."""
from __future__ import annotations

import argparse
import getpass
import json
import os
import re
import sqlite3
import sys
from dataclasses import asdict, dataclass, field
from datetime import timedelta
from pathlib import Path

from . import audit, auth, settings
from .store import backup as backup_db
from .store import connect

ROLES = ("ngo_admin", "ngo_staff", "student", "employer")
NGO_ROLES = ("ngo_admin", "ngo_staff")
USERNAME_RE = re.compile(r"^[a-z0-9._-]{3,32}$")
EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,190}\.[A-Za-z]{2,}$")


def clean_email(email: str | None) -> str | None:
    """None for blank. Raises AuthError for something that is not an email address."""
    e = (email or "").strip()
    if not e:
        return None
    if not EMAIL_RE.match(e):
        raise auth.AuthError("That email address does not look right.")
    return e.lower()


@dataclass
class User:
    id: int
    username: str
    display_name: str
    role: str
    student_id: str | None = None
    is_active: bool = True
    must_change_password: bool = False
    locked_until: str | None = None
    last_login_at: str | None = None
    created_at: str = ""
    listings: list[str] = field(default_factory=list)
    email: str | None = None

    @property
    def is_ngo(self) -> bool:
        return self.role in NGO_ROLES

    def public(self) -> dict:
        return asdict(self)


def _listings(conn: sqlite3.Connection, user_id: int) -> list[str]:
    return [r["opp_id"] for r in conn.execute("SELECT opp_id FROM listing_owners WHERE user_id = ? ORDER BY opp_id", (user_id,))]


def _user(conn: sqlite3.Connection, row: sqlite3.Row | None) -> User | None:
    if row is None:
        return None
    return User(id=row["id"], username=row["username"], display_name=row["display_name"], role=row["role"],
                student_id=row["student_id"], is_active=bool(row["is_active"]),
                must_change_password=bool(row["must_change_password"]), locked_until=row["locked_until"],
                last_login_at=row["last_login_at"], created_at=row["created_at"], listings=_listings(conn, row["id"]),
                email=row["email"])


def get_user(user_id: int, path: Path | str | None = None) -> User | None:
    c = connect(path)
    try:
        return _user(c, c.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone())
    finally:
        c.close()


def get_by_username(username: str, path: Path | str | None = None) -> User | None:
    c = connect(path)
    try:
        return _user(c, c.execute("SELECT * FROM users WHERE username = ?", (username.strip().lower(),)).fetchone())
    finally:
        c.close()


def list_users(path: Path | str | None = None) -> list[User]:
    c = connect(path)
    try:
        return [_user(c, r) for r in c.execute("SELECT * FROM users ORDER BY role, username")]  # type: ignore[misc]
    finally:
        c.close()


def count_users(path: Path | str | None = None) -> int:
    c = connect(path)
    try:
        return c.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    finally:
        c.close()


def create_user(username: str, display_name: str, role: str, *, password: str | None = None,
                student_id: str | None = None, listings: list[str] | tuple[str, ...] = (),
                must_change: bool = True, email: str | None = None, path: Path | str | None = None) -> tuple[User, str | None]:
    """Create an account. With no password a temporary one is made and returned once."""
    username = username.strip().lower()
    display_name = display_name.strip()
    if not USERNAME_RE.match(username):
        raise auth.AuthError("A username is 3 to 32 characters: letters, numbers, dot, dash or underscore.")
    if not display_name or len(display_name) > 80:
        raise auth.AuthError("Give a display name of up to 80 characters.")
    if role not in ROLES:
        raise auth.AuthError("Unknown role.")
    if role == "student" and not student_id:
        raise auth.AuthError("A student account must be linked to a student ID.")
    if role in NGO_ROLES and (student_id or listings):
        raise auth.AuthError("NGO accounts are not linked to a student or a listing.")
    if role != "student":
        student_id = None
    email = clean_email(email)
    temp = None
    if password is None:
        password = temp = auth.temp_password()
    else:
        auth.check_password_policy(password, username)
    c = connect(path)
    try:
        try:
            cur = c.execute(
                "INSERT INTO users (username, display_name, password_hash, role, student_id, must_change_password, created_at, email)"
                " VALUES (?,?,?,?,?,?,?,?)",
                (username, display_name, auth.hash_password(password), role, student_id, int(must_change), auth.iso(auth.now()), email))
        except sqlite3.IntegrityError as e:
            if "student_id" in str(e):
                raise auth.AuthError("That student already has an account.") from e
            raise auth.AuthError("That username is taken.") from e
        for opp in dict.fromkeys(listings):
            c.execute("INSERT INTO listing_owners (user_id, opp_id) VALUES (?,?)", (cur.lastrowid, opp))
        return _user(c, c.execute("SELECT * FROM users WHERE id = ?", (cur.lastrowid,)).fetchone()), temp  # type: ignore[return-value]
    finally:
        c.close()


def authenticate(username: str, password: str, ip: str | None = None, path: Path | str | None = None) -> User:
    """Check a sign-in. Raises AuthError with the same public message for every failure."""
    generic = "Wrong username or password."
    c = connect(path)
    try:
        row = c.execute("SELECT * FROM users WHERE username = ?", (username.strip().lower(),)).fetchone()
        if row is None:
            auth.burn_time()
            audit.record("login.failed", target=username.strip().lower()[:40], ip=ip, detail="unknown user", conn=c)
            raise auth.AuthError(generic, "unknown user")
        who = {"id": row["id"], "username": row["username"], "role": row["role"]}
        now = auth.now()
        if row["locked_until"] and auth.parse(row["locked_until"]) > now:
            auth.burn_time()
            audit.record("login.blocked", user=who, ip=ip, detail="account locked", conn=c)
            raise auth.AuthError(generic + " This account is locked for a while.", "locked")
        if not auth.verify_password(password, row["password_hash"]):
            failed = row["failed_logins"] + 1
            if failed >= auth.MAX_FAILED:
                c.execute("UPDATE users SET failed_logins = 0, locked_until = ? WHERE id = ?",
                          (auth.iso(now + timedelta(minutes=auth.LOCK_MINUTES)), row["id"]))
                audit.record("login.locked", user=who, ip=ip, detail=f"{auth.MAX_FAILED} failures", conn=c)
            else:
                c.execute("UPDATE users SET failed_logins = ? WHERE id = ?", (failed, row["id"]))
            audit.record("login.failed", user=who, ip=ip, detail="wrong password", conn=c)
            raise auth.AuthError(generic, "wrong password")
        if not row["is_active"]:
            audit.record("login.blocked", user=who, ip=ip, detail="account deactivated", conn=c)
            raise auth.AuthError(generic, "deactivated")
        new_hash = auth.hash_password(password) if auth.needs_rehash(row["password_hash"]) else row["password_hash"]
        c.execute("UPDATE users SET failed_logins = 0, locked_until = NULL, last_login_at = ?, password_hash = ? WHERE id = ?",
                  (auth.iso(now), new_hash, row["id"]))
        audit.record("login.ok", user=who, ip=ip, conn=c)
        return _user(c, c.execute("SELECT * FROM users WHERE id = ?", (row["id"],)).fetchone())  # type: ignore[return-value]
    finally:
        c.close()


def demo_sign_in(username: str, ip: str | None = None, path: Path | str | None = None) -> User:
    """Sign in without a password. Only the demo-login endpoint may call this, and only when DEMO_LOGIN=1."""
    if not settings.demo_login() or settings.cookie_secure():
        raise auth.AuthError("Demo sign-in is off.")
    c = connect(path)
    try:
        row = c.execute("SELECT * FROM users WHERE username = ?", (username.strip().lower(),)).fetchone()
        if row is None or not row["is_active"]:
            raise auth.AuthError("No such account.")
        c.execute("UPDATE users SET must_change_password = 0, failed_logins = 0, locked_until = NULL, last_login_at = ? WHERE id = ?",
                  (auth.iso(auth.now()), row["id"]))
        audit.record("login.demo", user={"id": row["id"], "username": row["username"], "role": row["role"]}, ip=ip, conn=c)
        return _user(c, c.execute("SELECT * FROM users WHERE id = ?", (row["id"],)).fetchone())  # type: ignore[return-value]
    finally:
        c.close()


def change_password(user_id: int, old: str, new: str, keep_token: str | None = None, path: Path | str | None = None) -> None:
    c = connect(path)
    try:
        row = c.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        if row is None or not auth.verify_password(old, row["password_hash"]):
            raise auth.AuthError("The current password is wrong.")
        auth.check_password_policy(new, row["username"])
        if auth.verify_password(new, row["password_hash"]):
            raise auth.AuthError("Choose a password that is different from the current one.")
        c.execute("UPDATE users SET password_hash = ?, must_change_password = 0 WHERE id = ?", (auth.hash_password(new), user_id))
        auth.revoke_sessions(c, user_id, keep_token)
    finally:
        c.close()


def reset_password(user_id: int, path: Path | str | None = None) -> str:
    temp = auth.temp_password()
    c = connect(path)
    try:
        n = c.execute("UPDATE users SET password_hash = ?, must_change_password = 1, failed_logins = 0, locked_until = NULL WHERE id = ?",
                      (auth.hash_password(temp), user_id)).rowcount
        if n == 0:
            raise auth.AuthError("No such account.")
        auth.revoke_sessions(c, user_id)
        return temp
    finally:
        c.close()


def _active_admins(c: sqlite3.Connection) -> int:
    return c.execute("SELECT COUNT(*) FROM users WHERE role = 'ngo_admin' AND is_active = 1").fetchone()[0]


def set_active(user_id: int, active: bool, path: Path | str | None = None) -> None:
    c = connect(path)
    try:
        row = c.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        if row is None:
            raise auth.AuthError("No such account.")
        if not active and row["role"] == "ngo_admin" and row["is_active"] and _active_admins(c) <= 1:
            raise auth.AuthError("This is the last active admin. Make another admin first.")
        c.execute("UPDATE users SET is_active = ? WHERE id = ?", (int(active), user_id))
        if not active:
            auth.revoke_sessions(c, user_id)
    finally:
        c.close()


def set_listings(user_id: int, listings: list[str], path: Path | str | None = None) -> None:
    c = connect(path)
    try:
        row = c.execute("SELECT role FROM users WHERE id = ?", (user_id,)).fetchone()
        if row is None or row["role"] != "employer":
            raise auth.AuthError("Only employer accounts own listings.")
        c.execute("DELETE FROM listing_owners WHERE user_id = ?", (user_id,))
        for opp in dict.fromkeys(listings):
            c.execute("INSERT INTO listing_owners (user_id, opp_id) VALUES (?,?)", (user_id, opp))
    finally:
        c.close()


def set_display_name(user_id: int, name: str, path: Path | str | None = None) -> None:
    name = name.strip()
    if not name or len(name) > 80:
        raise auth.AuthError("Give a display name of up to 80 characters.")
    c = connect(path)
    try:
        c.execute("UPDATE users SET display_name = ? WHERE id = ?", (name, user_id))
    finally:
        c.close()


def set_email(user_id: int, email: str | None, path: Path | str | None = None) -> None:
    """The address for emails about listings and interviews. Students' accounts never hold one (contacts.csv does)."""
    e = clean_email(email)
    c = connect(path)
    try:
        row = c.execute("SELECT role FROM users WHERE id = ?", (user_id,)).fetchone()
        if row is None:
            raise auth.AuthError("No such account.")
        if row["role"] == "student" and e:
            raise auth.AuthError("Student emails live in the private contact list, not on the account.")
        c.execute("UPDATE users SET email = ? WHERE id = ?", (e, user_id))
    finally:
        c.close()


def emails_of(user_ids: list[int], path: Path | str | None = None) -> list[str]:
    if not user_ids:
        return []
    c = connect(path)
    try:
        return [r["email"] for r in c.execute(f"SELECT email FROM users WHERE id IN ({','.join('?' * len(user_ids))}) AND email IS NOT NULL AND is_active = 1", user_ids)]
    finally:
        c.close()


def bootstrap_admin_if_empty(path: Path | str | None = None) -> bool:
    """Make the first admin from BOOTSTRAP_ADMIN_* when there are no users at all."""
    creds = settings.bootstrap_admin()
    if not creds or count_users(path) > 0:
        return False
    create_user(creds[0], "Administrator", "ngo_admin", password=creds[1], must_change=True, path=path)
    return True


# ---------- command line ----------

def _cmd_create_admin(a: argparse.Namespace) -> int:
    pw = os.environ.get("ADMIN_PASSWORD") or getpass.getpass("Password: ")
    if not os.environ.get("ADMIN_PASSWORD") and getpass.getpass("Again: ") != pw:
        print("The passwords do not match.", file=sys.stderr)
        return 1
    try:
        u, _ = create_user(a.username, a.name or a.username, "ngo_admin", password=pw, must_change=False)
    except auth.AuthError as e:
        print(e.public, file=sys.stderr)
        return 1
    print(f"Created admin {u.username}.")
    return 0


def _cmd_seed_demo(_: argparse.Namespace) -> int:
    if settings.cookie_secure():
        print("Refusing to make demo accounts when COOKIE_SECURE=1.", file=sys.stderr)
        return 1
    pw = os.environ.get("DEMO_PASSWORD", "")
    if not pw:
        print("Set DEMO_PASSWORD first.", file=sys.stderr)
        return 1
    plan = [("admin", "Demo Admin", "ngo_admin", {"email": "admin@ngo.example.org"}),
            ("officer", "Demo Officer", "ngo_staff", {"email": "officer@ngo.example.org"}),
            ("s001", "Lakshmi", "student", {"student_id": "S001"}), ("s002", "Ravi", "student", {"student_id": "S002"}),
            ("s003", "Divya", "student", {"student_id": "S003"}),
            ("gopuram", "Gopuram Software", "employer", {"listings": ["J028", "J027"], "email": "hr@gopuram.example.com"})]
    fresh = False
    for username, name, role, extra in plan:
        if get_by_username(username):
            print(f"skip {username} (exists)")
            continue
        create_user(username, name, role, password=pw, must_change=False, **extra)
        fresh = fresh or username == "gopuram"
        print(f"created {username} ({role})")
    if fresh:  # something for the NGO to act on the first time the demo opens
        from . import applications, listings
        owner = get_by_username("gopuram")
        listings.create(owner.id, listings.ListingIn(  # type: ignore[union-attr]
            title="Junior Python Developer (Remote)", org_name="Gopuram Software", required_skills_text="Python, SQL, Git, Django is a plus",
            mode="remote", pay_text="4.2 LPA", hours_per_week=40, openings=2,
            description="Build and test small features with a friendly team."), submit=True)
        applications.create("S001", "J028", "I have used Excel and SQL in my projects.")
        from . import contacts
        for sid in ("S001", "S002", "S003"):     # the three demo students agreed to WhatsApp updates
            contacts.set_opt_in(sid, True, "seed-demo")
        print("created one listing waiting for review and one interested student")
    return 0


def _cmd_seed_outcomes(_: argparse.Namespace) -> int:
    """Sample staff decisions, so a demo can show the learned score. They come from the rule score, so they show how the
    learning works, not that it makes matches better. They are marked "sample". Never in secure mode."""
    if settings.cookie_secure():
        print("Refusing to make sample outcomes when COOKIE_SECURE=1.", file=sys.stderr)
        return 1
    import pandas as pd

    from . import db
    from .config import PATHS
    from .schema import Decision
    if any(d.decided_by == "sample" for d in db.list_decisions()):
        print("skip (sample outcomes exist)")
        return 0
    kinds = {o["opp_id"]: o["type"] for o in json.loads(Path(PATHS["opportunities"]).read_text())}
    rows = pd.read_csv(PATHS["pair_scores"])
    rows = rows[rows["eligible"] & (rows["opp_id"].map(kinds) == "job")]
    jobs = rows.sort_values(["coverage", "student_id", "opp_id"], ascending=[False, True, True])
    note = "Sample outcome for the demo."
    for r in jobs.head(15).itertuples():
        db.save_decision(Decision(student_id=r.student_id, opp_id=r.opp_id, decision="accept", note=note), decided_by="sample")
    for r in jobs.tail(15).itertuples():
        db.save_decision(Decision(student_id=r.student_id, opp_id=r.opp_id, decision="reject", reject_reason="skills gap", note=note), decided_by="sample")
    print("created 30 sample outcomes (15 yes, 15 no)")
    return 0


def _cmd_backup(a: argparse.Namespace) -> int:
    print(backup_db(a.folder))
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m matcher.accounts")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("create-admin", help="make an NGO admin (asks for the password)")
    p.add_argument("--username", required=True)
    p.add_argument("--name", default="")
    p.set_defaults(fn=_cmd_create_admin)
    sub.add_parser("seed-demo", help="make demo accounts (needs DEMO_PASSWORD, never in secure mode)").set_defaults(fn=_cmd_seed_demo)
    sub.add_parser("seed-outcomes", help="make sample decisions so a demo can show the learned score, never in secure mode").set_defaults(fn=_cmd_seed_outcomes)
    p = sub.add_parser("backup", help="copy the database safely")
    p.add_argument("folder")
    p.set_defaults(fn=_cmd_backup)
    a = ap.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    raise SystemExit(main())
