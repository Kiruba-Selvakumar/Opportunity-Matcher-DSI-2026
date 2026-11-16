"""Google Calendar and Meet: one NGO Google account, connected once by an admin.

Every interview becomes an event on that account's calendar with a Meet link, and Google sends the invites. Guests
cannot see each other, so an employer never gets a student's email from the invite. Only the refresh token is stored
(in the database, next to everything else private); access tokens live in memory for an hour.
"""
from __future__ import annotations

import base64
import json
import secrets
import time
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urlencode

from . import auth, integrations, settings, standins
from .store import connect

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
REVOKE_URL = "https://oauth2.googleapis.com/revoke"
API = "https://www.googleapis.com/calendar/v3/calendars/primary/events"
SCOPES = "openid email https://www.googleapis.com/auth/calendar.events"
STATE_MINUTES = 10
_token: dict = {"value": None, "expires": 0.0}


class GoogleError(RuntimeError):
    """Google refused or is not set up. The message is safe to show to an admin."""


def _http(method: str, url: str, **kw):
    """Every call to Google goes through here, so tests can replace it."""
    import httpx
    return httpx.request(method, url, timeout=20, **kw)


def _cfg() -> dict:
    cfg = settings.google()
    if cfg is None:
        raise GoogleError("Google is not set up. Add GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET to .env.")
    return cfg


def connected() -> bool:
    return settings.google() is not None and integrations.get("google") is not None


# ---- connecting (OAuth) ----

def start(user_id: int, path: Path | str | None = None) -> str:
    """The Google consent page to send the admin to. The state ties the answer to this admin for 10 minutes."""
    cfg = _cfg()
    state = secrets.token_urlsafe(24)
    c = connect(path)
    try:
        c.execute("DELETE FROM oauth_states WHERE created_at < ?", (auth.iso(auth.now() - timedelta(minutes=STATE_MINUTES)),))
        c.execute("INSERT INTO oauth_states (state, user_id, created_at) VALUES (?,?,?)", (state, user_id, auth.iso(auth.now())))
    finally:
        c.close()
    return AUTH_URL + "?" + urlencode({"client_id": cfg["client_id"], "redirect_uri": cfg["redirect_uri"], "response_type": "code",
                                       "scope": SCOPES, "access_type": "offline", "prompt": "consent", "state": state,
                                       "include_granted_scopes": "true"})


def _email_from_id_token(id_token: str | None) -> str | None:
    """The id_token came straight from Google's token endpoint over TLS, so reading its payload is enough here."""
    if not id_token or id_token.count(".") != 2:
        return None
    part = id_token.split(".")[1]
    try:
        return json.loads(base64.urlsafe_b64decode(part + "=" * (-len(part) % 4))).get("email")
    except ValueError:
        return None


def finish(state: str, code: str, user_id: int, username: str, path: Path | str | None = None) -> str:
    """Exchange the code Google sent back and store the connection. Returns the connected account's email."""
    cfg = _cfg()
    c = connect(path)
    try:
        row = c.execute("SELECT * FROM oauth_states WHERE state = ?", (state or "",)).fetchone()
        c.execute("DELETE FROM oauth_states WHERE state = ?", (state or "",))
    finally:
        c.close()
    if row is None or row["user_id"] != user_id or auth.parse(row["created_at"]) < auth.now() - timedelta(minutes=STATE_MINUTES):
        raise GoogleError("This sign-in link is old or was not started here. Start again from Settings.")
    r = _http("POST", TOKEN_URL, data={"code": code, "client_id": cfg["client_id"], "client_secret": cfg["client_secret"],
                                       "redirect_uri": cfg["redirect_uri"], "grant_type": "authorization_code"})
    data = r.json()
    if r.status_code >= 400 or not data.get("refresh_token"):
        raise GoogleError(data.get("error_description") or "Google did not give a lasting connection. Try again.")
    email = _email_from_id_token(data.get("id_token"))
    integrations.put("google", {"refresh_token": data["refresh_token"], "email": email, "scope": data.get("scope", "")}, username, path)
    _token.update(value=data.get("access_token"), expires=time.time() + int(data.get("expires_in", 0)) - 60)
    return email or "your Google account"


def disconnect(path: Path | str | None = None) -> None:
    g = integrations.get("google", path)
    if g and g.get("refresh_token"):
        try:
            _http("POST", REVOKE_URL, params={"token": g["refresh_token"]})
        except Exception:  # noqa: BLE001 - forget it locally even if Google cannot be reached
            pass
    integrations.remove("google", path)
    _token.update(value=None, expires=0.0)


def _access_token() -> str:
    if _token["value"] and time.time() < _token["expires"]:
        return _token["value"]
    cfg = _cfg()
    g = integrations.get("google")
    if not g:
        raise GoogleError("No Google account is connected. An admin can connect one in Settings.")
    r = _http("POST", TOKEN_URL, data={"client_id": cfg["client_id"], "client_secret": cfg["client_secret"],
                                       "refresh_token": g["refresh_token"], "grant_type": "refresh_token"})
    data = r.json()
    if r.status_code >= 400:
        raise GoogleError("Google stopped accepting the connection. An admin should connect it again in Settings.")
    _token.update(value=data["access_token"], expires=time.time() + int(data.get("expires_in", 3600)) - 60)
    return _token["value"]


def _call(method: str, url: str, **kw) -> dict:
    r = _http(method, url, headers={"Authorization": f"Bearer {_access_token()}"}, **kw)
    if r.status_code == 204:
        return {}
    data = r.json() if r.content else {}
    if r.status_code >= 400:
        raise GoogleError((data.get("error") or {}).get("message") or f"Google said {r.status_code}.")
    return data


# ---- events ----

def _times(start: datetime, minutes: int) -> dict:
    tz = settings.timezone()
    return {"start": {"dateTime": start.isoformat(), "timeZone": tz},
            "end": {"dateTime": (start + timedelta(minutes=minutes)).isoformat(), "timeZone": tz}}


def create_event(summary: str, description: str, start: datetime, minutes: int, attendees: list[str],
                 location: str | None = None, with_meet: bool = True) -> dict:
    """Make the event and, if asked, a Meet link. Google emails the invite to every attendee."""
    body = {"summary": summary, "description": description, **_times(start, minutes),
            "attendees": [{"email": a} for a in dict.fromkeys(standins.calendar_guests(attendees)) if a],
            "guestsCanSeeOtherGuests": False, "guestsCanInviteOthers": False,
            "reminders": {"useDefault": True}}
    if location:
        body["location"] = location
    if with_meet:
        body["conferenceData"] = {"createRequest": {"requestId": uuid.uuid4().hex, "conferenceSolutionKey": {"type": "hangoutsMeet"}}}
    data = _call("POST", API, params={"conferenceDataVersion": 1, "sendUpdates": "all"}, json=body)
    link = data.get("hangoutLink") or next((e.get("uri") for e in (data.get("conferenceData") or {}).get("entryPoints", [])
                                            if e.get("entryPointType") == "video"), None)
    return {"id": data["id"], "meet_link": link, "html_link": data.get("htmlLink")}


def move_event(event_id: str, start: datetime, minutes: int) -> None:
    _call("PATCH", f"{API}/{event_id}", params={"sendUpdates": "all"}, json=_times(start, minutes))


def cancel_event(event_id: str) -> None:
    _call("DELETE", f"{API}/{event_id}", params={"sendUpdates": "all"})
