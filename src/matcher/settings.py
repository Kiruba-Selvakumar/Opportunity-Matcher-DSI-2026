"""Settings from the environment, read when they are used so tests can change them."""
from __future__ import annotations

import os
import secrets
from pathlib import Path

_dev_salt = secrets.token_hex(16)  # only used when CANDIDATE_SALT is not set (development)


def load_env_file(path: Path | None = None) -> None:
    """Read the repo's .env into the environment, without overriding what is already set. Docker passes it as env_file;
    this makes `make app` and plain uvicorn see the same settings from the start. Tests set MATCHER_DOTENV=0, so real
    keys in .env can never make a test send a real email or WhatsApp message."""
    if os.environ.get("MATCHER_DOTENV", "1") == "0":
        return
    try:
        from dotenv import load_dotenv
        load_dotenv(path or Path(__file__).resolve().parents[2] / ".env", override=False)
    except ImportError:
        pass


load_env_file()


def _int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, "").strip() or default)
    except ValueError:
        return default


def cookie_secure() -> bool:
    return os.environ.get("COOKIE_SECURE", "0").strip() in {"1", "true", "yes"}


def demo_login() -> bool:
    return os.environ.get("DEMO_LOGIN", "0").strip() in {"1", "true", "yes"}


def session_hours() -> int:
    return _int("SESSION_HOURS", 12)


def session_idle_hours() -> int:
    return _int("SESSION_IDLE_HOURS", 2)


def candidate_salt() -> str:
    return os.environ.get("CANDIDATE_SALT", "").strip() or _dev_salt


def bootstrap_admin() -> tuple[str, str] | None:
    u = os.environ.get("BOOTSTRAP_ADMIN_USERNAME", "").strip()
    p = os.environ.get("BOOTSTRAP_ADMIN_PASSWORD", "")
    return (u, p) if u and p else None


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, "").strip() or default


def app_url() -> str:
    """Where people open the app, for links in emails and WhatsApp messages."""
    return _env("APP_URL", "http://localhost:5173").rstrip("/")


def sync_delivery() -> bool:
    """1 = send emails and WhatsApp messages inside the request (tests). Otherwise a background thread sends them."""
    return _env("OUTBOX_SYNC", "0") in {"1", "true", "yes"}


# ---- email (any SMTP server: Gmail app password, Zoho, SES, ...) ----

def smtp() -> dict | None:
    host = _env("SMTP_HOST")
    if not host:
        return None
    return {"host": host, "port": _int("SMTP_PORT", 587), "user": _env("SMTP_USER"), "password": os.environ.get("SMTP_PASSWORD", ""),
            "from": _env("SMTP_FROM", _env("SMTP_USER")), "ssl": _env("SMTP_SSL", "0") in {"1", "true", "yes"}}


# ---- WhatsApp (Meta Cloud API) ----

def whatsapp() -> dict | None:
    token, number = _env("WHATSAPP_TOKEN"), _env("WHATSAPP_PHONE_NUMBER_ID")
    if not (token and number):
        return None
    return {"token": token, "phone_number_id": number, "version": _env("WHATSAPP_API_VERSION", "v21.0"),
            "lang": _env("WHATSAPP_TEMPLATE_LANG", "en")}


def whatsapp_template(kind: str) -> str:
    """The approved template name for each kind of bulk message (see README, "WhatsApp templates")."""
    defaults = {"opportunity": "new_opportunity", "matches": "matches_ready", "update": "ngo_update", "interview": "interview_scheduled"}
    return _env(f"WHATSAPP_TEMPLATE_{kind.upper()}", defaults[kind])


def whatsapp_only_to() -> str:
    """Comma-separated numbers. When set, WhatsApp goes only to these (for testing with real accounts)."""
    return os.environ.get("WHATSAPP_ONLY_TO", "")


def whatsapp_verify_token() -> str:
    return _env("WHATSAPP_VERIFY_TOKEN")


def whatsapp_app_secret() -> str:
    return _env("WHATSAPP_APP_SECRET")


# ---- Google Calendar and Meet ----

def google() -> dict | None:
    cid, secret = _env("GOOGLE_CLIENT_ID"), _env("GOOGLE_CLIENT_SECRET")
    if not (cid and secret):
        return None
    api = _env("API_URL", app_url())
    return {"client_id": cid, "client_secret": secret,
            "redirect_uri": _env("GOOGLE_REDIRECT_URI", f"{api}/api/integrations/google/callback"),
            "timezone": _env("TIMEZONE", "Asia/Kolkata")}


def timezone() -> str:
    return _env("TIMEZONE", "Asia/Kolkata")


# ---- Fireflies notetaker ----

def fireflies() -> dict | None:
    key = _env("FIREFLIES_API_KEY")
    if not key:
        return None
    return {"api_key": key, "bot_email": _env("FIREFLIES_BOT_EMAIL", "fred@fireflies.ai"),
            "webhook_secret": os.environ.get("FIREFLIES_WEBHOOK_SECRET", "")}


# ---- test stand-ins (see standins.py) ----

def standin_whatsapp() -> str:
    return os.environ.get("STANDIN_WHATSAPP", "")


def standin_email() -> str:
    return os.environ.get("STANDIN_EMAIL", "")


def check_production_ready() -> list[str]:
    """Problems that must stop the app from starting."""
    from . import contacts, standins
    problems = standins.problems()
    if whatsapp() and not standins.active() and not whatsapp_only_to().strip() and contacts.looks_like_sample():
        problems.append("WhatsApp is live but these are the sample students, whose made-up numbers may belong to real people. "
                        "Set STANDIN_WHATSAPP to test, or load your real data to go live.")
    if cookie_secure() and len(os.environ.get("CANDIDATE_SALT", "")) < 16:
        problems.append("Set CANDIDATE_SALT to a long random value (at least 16 characters) when COOKIE_SECURE=1.")
    if cookie_secure() and demo_login():
        problems.append("DEMO_LOGIN=1 lets anyone sign in without a password, so it cannot be used with COOKIE_SECURE=1.")
    if cookie_secure() and whatsapp() and not whatsapp_app_secret():
        problems.append("Set WHATSAPP_APP_SECRET so the WhatsApp webhook only accepts messages signed by Meta.")
    if cookie_secure() and fireflies() and not fireflies()["webhook_secret"]:  # type: ignore[index]
        problems.append("Set FIREFLIES_WEBHOOK_SECRET so the Fireflies webhook only accepts signed calls.")
    return problems
