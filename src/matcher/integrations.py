"""Connected services: what is set up, and the stored Google connection. Secrets in the environment are never returned."""
from __future__ import annotations

import json
from pathlib import Path

from . import auth, settings, standins
from .store import connect


def get(name: str, path: Path | str | None = None) -> dict | None:
    c = connect(path)
    try:
        r = c.execute("SELECT data, updated_by, updated_at FROM integrations WHERE name = ?", (name,)).fetchone()
        return {**json.loads(r["data"]), "updated_by": r["updated_by"], "updated_at": r["updated_at"]} if r else None
    finally:
        c.close()


def put(name: str, data: dict, by: str, path: Path | str | None = None) -> None:
    c = connect(path)
    try:
        c.execute("INSERT INTO integrations (name, data, updated_by, updated_at) VALUES (?,?,?,?) ON CONFLICT(name) DO UPDATE SET "
                  "data = excluded.data, updated_by = excluded.updated_by, updated_at = excluded.updated_at",
                  (name, json.dumps(data), by, auth.iso(auth.now())))
    finally:
        c.close()


def remove(name: str, path: Path | str | None = None) -> bool:
    c = connect(path)
    try:
        return c.execute("DELETE FROM integrations WHERE name = ?", (name,)).rowcount > 0
    finally:
        c.close()


def status() -> dict:
    """What an admin sees on the Settings page. True means the service is live; false means messages are dry runs."""
    g = get("google")
    smtp = settings.smtp()
    wa = settings.whatsapp()
    ff = settings.fireflies()
    return {
        "email": {"live": smtp is not None, "from": smtp["from"] if smtp else None},
        "whatsapp": {"live": wa is not None, "webhook_ready": bool(settings.whatsapp_verify_token() and settings.whatsapp_app_secret()),
                     "only_to": len([x for x in settings.whatsapp_only_to().split(",") if x.strip()]),
                     "templates": {k: settings.whatsapp_template(k) for k in ("opportunity", "matches", "update", "interview")}},
        "google": {"configured": settings.google() is not None, "connected": g is not None,
                   "account": g.get("email") if g else None, "connected_by": g.get("updated_by") if g else None,
                   "connected_at": g.get("updated_at") if g else None},
        "fireflies": {"live": ff is not None, "bot_email": ff["bot_email"] if ff else None,
                      "webhook_ready": bool(ff and ff["webhook_secret"])},
        "test_mode": {"active": standins.active()},
        "app_url": settings.app_url(),
    }
