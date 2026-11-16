"""Passwords, sessions, CSRF tokens and sign-in throttling. No web framework code lives here."""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import sqlite3
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone

from . import settings

SCRYPT_N, SCRYPT_R, SCRYPT_P = 2**14, 8, 1
MIN_PASSWORD = 10
MAX_PASSWORD = 128
MAX_FAILED = 5
LOCK_MINUTES = 15
IP_ATTEMPTS, IP_WINDOW_SECONDS = 20, 600

COMMON_PASSWORDS = {
    "password", "password1", "password12", "password123", "passw0rd123", "1234567890", "12345678910",
    "qwertyuiop", "qwerty12345", "iloveyou123", "welcome123", "welcome1234", "admin12345", "administrator",
    "letmein1234", "abcd123456", "abc1234567", "changeme123", "changemenow", "0123456789", "9876543210",
    "india12345", "india123456", "hyderabad123", "barabari123", "student1234", "employer123",
}


class AuthError(Exception):
    """Sign-in or password problem. `public` is safe to show, `reason` goes to the audit log."""

    def __init__(self, public: str, reason: str = "") -> None:
        super().__init__(public)
        self.public = public
        self.reason = reason or public


def now() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime) -> str:
    return dt.isoformat(timespec="seconds")


def parse(ts: str) -> datetime:
    return datetime.fromisoformat(ts)


# ---------- passwords ----------

def _b64(b: bytes) -> str:
    return base64.b64encode(b).decode()


def hash_password(password: str, n: int = SCRYPT_N, r: int = SCRYPT_R, p: int = SCRYPT_P) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=n, r=r, p=p, dklen=32, maxmem=128 * n * r * 2)
    return f"scrypt${n}${r}${p}${_b64(salt)}${_b64(digest)}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, n, r, p, salt, digest = stored.split("$")
        if scheme != "scrypt":
            return False
        n, r, p = int(n), int(r), int(p)
        got = hashlib.scrypt(password.encode(), salt=base64.b64decode(salt), n=n, r=r, p=p, dklen=32,
                             maxmem=128 * n * r * 2)
        return hmac.compare_digest(got, base64.b64decode(digest))
    except (ValueError, TypeError):
        return False


def needs_rehash(stored: str) -> bool:
    try:
        _, n, r, p, _, _ = stored.split("$")
        return (int(n), int(r), int(p)) != (SCRYPT_N, SCRYPT_R, SCRYPT_P)
    except ValueError:
        return True


_DUMMY_HASH = hash_password("not-a-real-password-" + secrets.token_hex(4))


def burn_time() -> None:
    """Spend the same time as a real check, so an unknown username cannot be told apart by speed."""
    verify_password("x", _DUMMY_HASH)


def check_password_policy(password: str, username: str = "") -> None:
    if len(password) < MIN_PASSWORD:
        raise AuthError(f"Use at least {MIN_PASSWORD} characters.")
    if len(password) > MAX_PASSWORD:
        raise AuthError(f"Use at most {MAX_PASSWORD} characters.")
    low = password.lower()
    if username and low == username.lower():
        raise AuthError("The password cannot be the same as the username.")
    if low in COMMON_PASSWORDS:
        raise AuthError("That password is too common. Choose a different one.")


def temp_password() -> str:
    alphabet = "abcdefghjkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no look-alike letters
    return "".join(secrets.choice(alphabet) for _ in range(16))


# ---------- sessions ----------

def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_session(conn: sqlite3.Connection, user_id: int, ip: str | None = None, at: datetime | None = None) -> tuple[str, str]:
    """Returns (cookie token, csrf token). Only the hash of the cookie token is stored."""
    at = at or now()
    token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(24)
    conn.execute(
        "INSERT INTO sessions (token_hash, user_id, csrf_token, created_at, last_seen_at, expires_at, ip) VALUES (?,?,?,?,?,?,?)",
        (_token_hash(token), user_id, csrf, iso(at), iso(at), iso(at + timedelta(hours=settings.session_hours())), ip))
    return token, csrf


def load_session(conn: sqlite3.Connection, token: str | None, at: datetime | None = None) -> sqlite3.Row | None:
    """Return the session row if it is valid, and slide the idle timer. Expired sessions are deleted."""
    if not token:
        return None
    at = at or now()
    row = conn.execute("SELECT * FROM sessions WHERE token_hash = ?", (_token_hash(token),)).fetchone()
    if row is None:
        return None
    idle_limit = parse(row["last_seen_at"]) + timedelta(hours=settings.session_idle_hours())
    if at >= parse(row["expires_at"]) or at >= idle_limit:
        conn.execute("DELETE FROM sessions WHERE token_hash = ?", (row["token_hash"],))
        return None
    conn.execute("UPDATE sessions SET last_seen_at = ? WHERE token_hash = ?", (iso(at), row["token_hash"]))
    return row


def delete_session(conn: sqlite3.Connection, token: str | None) -> None:
    if token:
        conn.execute("DELETE FROM sessions WHERE token_hash = ?", (_token_hash(token),))


def revoke_sessions(conn: sqlite3.Connection, user_id: int, keep_token: str | None = None) -> int:
    keep = _token_hash(keep_token) if keep_token else ""
    return conn.execute("DELETE FROM sessions WHERE user_id = ? AND token_hash != ?", (user_id, keep)).rowcount


def csrf_ok(expected: str, given: str | None) -> bool:
    return bool(given) and hmac.compare_digest(expected, given or "")


# ---------- sign-in throttling by IP address ----------

_attempts: dict[str, deque] = defaultdict(deque)


def ip_allowed(ip: str, at: float | None = None) -> bool:
    t = at if at is not None else time.time()
    q = _attempts[ip]
    while q and q[0] < t - IP_WINDOW_SECONDS:
        q.popleft()
    return len(q) < IP_ATTEMPTS


def ip_note_attempt(ip: str, at: float | None = None) -> None:
    _attempts[ip].append(at if at is not None else time.time())


def ip_reset() -> None:
    _attempts.clear()


def list_sessions(conn: sqlite3.Connection, user_id: int, current_token: str | None = None) -> list[dict]:
    cur = _token_hash(current_token) if current_token else ""
    rows = conn.execute("SELECT token_hash, created_at, last_seen_at, ip FROM sessions WHERE user_id = ? ORDER BY last_seen_at DESC", (user_id,)).fetchall()
    return [{"created_at": r["created_at"], "last_seen_at": r["last_seen_at"], "ip": r["ip"], "current": r["token_hash"] == cur} for r in rows]
