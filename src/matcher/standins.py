"""Test stand-ins: while the data is fake, real messages go to people who agreed to test, and to nobody else.

Set STANDIN_WHATSAPP and STANDIN_EMAIL in .env as "who=where, who=where". who is a student ID (S001), a username (admin,
gopuram) or * for everyone not named. In STANDIN_WHATSAPP, * means every student, and a phone under any name that is not a
student (admin, lead) plays an employer writing in, because only students get WhatsApp messages from the app.

The data is not touched. The swap happens just before a message leaves, so the app runs as it will with real people: each
person keeps their own fake address, and many people can share one stand-in without colliding anywhere.

While either setting is on, anyone without a stand-in gets a dry run. The sample phone numbers are made up but may belong
to strangers, so a message never falls through to them.

To go live, delete both settings. Every function here then hands back the real address, and nothing else changes.
"""
from __future__ import annotations

import re

from . import contacts, outbox, settings
from .store import connect

HELD = "Not sent: test mode is on and this person has no stand-in."
EVERYONE = "*"


def active() -> bool:
    return bool(settings.standin_whatsapp().strip() or settings.standin_email().strip())


def _pairs(raw: str, name: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for part in raw.split(","):
        if not part.strip():
            continue
        who, sep, where = part.partition("=")
        if not sep or not who.strip() or not where.strip():
            raise ValueError(f"{name}: \"{part.strip()}\" should look like who=where.")
        out[who.strip().lower()] = where.strip()
    return out


def _number(raw: str) -> str:
    """A number as Meta writes it: digits with the country code. Indian numbers may be written with ten digits."""
    return contacts.normalize_phone(raw) or re.sub(r"\D", "", raw)


def whatsapp_map() -> dict[str, str]:
    routes = _pairs(settings.standin_whatsapp(), "STANDIN_WHATSAPP")
    for who, where in routes.items():
        if len(_number(where)) < 8:
            raise ValueError(f"STANDIN_WHATSAPP: \"{where}\" for {who} is not a phone number.")
    return {who: _number(where) for who, where in routes.items()}


def email_map() -> dict[str, str]:
    routes = _pairs(settings.standin_email(), "STANDIN_EMAIL")
    for who, where in routes.items():
        if "@" not in where:
            raise ValueError(f"STANDIN_EMAIL: \"{where}\" for {who} is not an email address.")
    return {who: where.lower() for who, where in routes.items()}


def problems() -> list[str]:
    """Settings that cannot be read stop the app at start, so a typo never sends a message to the wrong place."""
    out = []
    for read in (whatsapp_map, email_map):
        try:
            read()
        except ValueError as e:
            out.append(str(e))
    return out


# ---- email ----

def _who_by_email(address: str) -> str | None:
    a = address.strip().lower()
    for sid, c in contacts.book().items():
        if c["email"].strip().lower() == a:
            return sid
    conn = connect()
    try:
        row = conn.execute("SELECT username FROM users WHERE LOWER(email) = ? ORDER BY id LIMIT 1", (a,)).fetchone()
    finally:
        conn.close()
    return row["username"] if row else None


def email_route(address: str, student_id: str | None = None) -> tuple[str, str] | None:
    """(the stand-in's address, who they stand in for), or None to hold the message. Call only when active()."""
    routes = email_map()
    who = student_id or _who_by_email(address) or address.strip().lower()
    target = routes.get(who.lower()) or routes.get(address.strip().lower()) or routes.get(EVERYONE)
    return (target, who) if target else None


def calendar_guests(addresses: list[str]) -> list[str]:
    """Google emails every guest on an event itself, so the guest list is swapped too. The notetaker bot is not a person."""
    if not active():
        return addresses
    bot = (settings.fireflies() or {}).get("bot_email")
    out = []
    for a in addresses:
        route = None if a == bot else email_route(a)
        if a == bot or route:
            out.append(a if a == bot else route[0])  # type: ignore[index]
    return out


# ---- WhatsApp ----

def whatsapp_for_student(student_id: str) -> str | None:
    """The stand-in's number, or None to hold the message. Call only when active()."""
    routes = whatsapp_map()
    return routes.get(student_id.lower()) or routes.get(EVERYONE)


def number_is_listed(phone: str) -> bool:
    """A reply to someone who wrote in goes only to a phone on the list."""
    return _number(phone) in whatsapp_map().values()


def _last_student_messaged(number: str) -> str | None:
    """One phone can stand in for every student, so a reply belongs to whoever that phone last heard about."""
    conn = connect()
    try:
        row = conn.execute("SELECT recipient FROM outbox WHERE channel = 'whatsapp' AND recipient LIKE 'student:%' AND address LIKE ? "
                           "AND status NOT IN ('dry_run', 'failed') ORDER BY id DESC LIMIT 1", (f"% via {outbox.mask(number)}",)).fetchone()
    finally:
        conn.close()
    return row["recipient"].removeprefix("student:") if row else None


def incoming_student(wa_id: str) -> str | None:
    """Which student an incoming WhatsApp number speaks for. None makes it an employer lead, as it would in production."""
    if active():
        n = _number(wa_id)
        for who, where in whatsapp_map().items():
            if where == n:
                if who == EVERYONE:
                    return _last_student_messaged(n) or next(iter(contacts.book()), None)
                return next((sid for sid in contacts.book() if sid.lower() == who), None)
    return contacts.student_by_phone(wa_id)
