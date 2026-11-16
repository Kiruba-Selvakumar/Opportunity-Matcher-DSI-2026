"""WhatsApp through Meta's Cloud API.

* Students get template messages (the only kind WhatsApp allows outside a 24 hour reply window), and only if they agreed.
* Employers who write to the NGO number become leads (leads.py). Staff reply with plain text inside the 24 hour window.
* Meta calls the webhook for incoming messages and delivery reports. Every call is checked against WHATSAPP_APP_SECRET.

With no WHATSAPP_TOKEN every message is a dry run in the outbox, so the app works the same without a Meta account.
"""
from __future__ import annotations

import hashlib
import hmac

from . import contacts, outbox, settings, standins

GRAPH = "https://graph.facebook.com"


class WhatsAppError(RuntimeError):
    """Meta refused the message. The text is Meta's own reason."""


def template_payload(to: str, name: str, lang: str, params: list[str]) -> dict:
    body = {"type": "body", "parameters": [{"type": "text", "text": str(p)[:500]} for p in params]}
    return {"messaging_product": "whatsapp", "to": to, "type": "template",
            "template": {"name": name, "language": {"code": lang}, "components": [body] if params else []}}


def text_payload(to: str, body: str) -> dict:
    return {"messaging_product": "whatsapp", "recipient_type": "individual", "to": to, "type": "text",
            "text": {"preview_url": False, "body": body[:4000]}}


def _post(cfg: dict, payload: dict) -> str:
    import httpx
    r = httpx.post(f"{GRAPH}/{cfg['version']}/{cfg['phone_number_id']}/messages", json=payload,
                   headers={"Authorization": f"Bearer {cfg['token']}"}, timeout=20)
    data = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
    if r.status_code >= 400 or not data.get("messages"):
        raise WhatsAppError((data.get("error") or {}).get("message") or f"HTTP {r.status_code}")
    return data["messages"][0]["id"]


def only_to() -> set[str]:
    """WHATSAPP_ONLY_TO: while testing, the only numbers that may get a real message. Empty means everyone who agreed."""
    return {contacts.normalize_phone(x) or x.strip() for x in settings.whatsapp_only_to().split(",") if x.strip()}


def _held_back(to: str) -> bool:
    allowed = only_to()
    return bool(allowed) and to not in allowed


HELD = "Not sent: WHATSAPP_ONLY_TO is set and this number is not on it."


def _deliver(oid: int, cfg: dict, payload: dict) -> None:
    try:
        outbox.mark(oid, "sent", provider_id=_post(cfg, payload))
    except Exception as e:  # noqa: BLE001 - recorded on the row, never raised into a request
        outbox.mark(oid, "failed", error=str(e))


def send_template(student_id: str, kind: str, params: list[str], preview: str, batch_id: str | None = None) -> int | None:
    """Queue a template message to a student. None when they have not agreed or have no usable number."""
    if student_id not in contacts.opted_in():
        return None
    to = contacts.phone(student_id)
    if not to:
        return None
    cfg = settings.whatsapp()
    shown, why_held = outbox.mask(to), None
    if standins.active():
        stand_in = standins.whatsapp_for_student(student_id)
        if stand_in:
            shown, to = f"{shown} via {outbox.mask(stand_in)}", stand_in
        else:
            why_held = standins.HELD
    if not why_held and cfg and _held_back(to):
        why_held = HELD
    oid = outbox.add("whatsapp", kind, f"student:{student_id}", shown, preview,
                     status="queued" if cfg and not why_held else "dry_run", batch_id=batch_id)
    if why_held:
        outbox.mark(oid, "dry_run", error=why_held)
    elif cfg:
        payload = template_payload(to, settings.whatsapp_template(kind), cfg["lang"], params)
        outbox.run(lambda: _deliver(oid, cfg, payload))
    return oid


def send_text(phone: str, body: str, *, kind: str, recipient: str) -> int:
    """A plain reply, for example to an employer lead. WhatsApp only delivers it within 24 hours of their last message."""
    cfg = settings.whatsapp()
    why_held = standins.HELD if standins.active() and not standins.number_is_listed(phone) else None
    if not why_held and cfg and _held_back(phone):
        why_held = HELD
    oid = outbox.add("whatsapp", kind, recipient, phone, body, status="queued" if cfg and not why_held else "dry_run")
    if why_held:
        outbox.mark(oid, "dry_run", error=why_held)
    elif cfg:
        payload = text_payload(phone, body)
        outbox.run(lambda: _deliver(oid, cfg, payload))
    return oid


# ---- webhook ----

def verify_signature(raw: bytes, header: str | None, secret: str) -> bool:
    """Meta signs every call: X-Hub-Signature-256 = "sha256=" + HMAC-SHA256(app secret, raw body)."""
    if not secret or not header or not header.startswith("sha256="):
        return False
    good = hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    return hmac.compare_digest(good, header.removeprefix("sha256="))


def parse_webhook(payload: dict) -> tuple[list[dict], list[dict]]:
    """(incoming text messages, delivery reports) from one webhook call. Other message types are noted, not stored."""
    messages, statuses = [], []
    for entry in payload.get("entry") or []:
        for change in entry.get("changes") or []:
            v = change.get("value") or {}
            names = {c.get("wa_id"): (c.get("profile") or {}).get("name") for c in v.get("contacts") or []}
            for m in v.get("messages") or []:
                kind = m.get("type")
                text = (m.get("text") or {}).get("body") if kind == "text" else f"[{kind} message: open WhatsApp to see it]"
                messages.append({"from": m.get("from", ""), "id": m.get("id", ""), "text": text or "",
                                 "name": names.get(m.get("from")), "timestamp": m.get("timestamp")})
            for s in v.get("statuses") or []:
                err = (s.get("errors") or [{}])[0]
                statuses.append({"id": s.get("id", ""), "status": s.get("status", ""),
                                 "error": err.get("title") or err.get("message")})
    return messages, statuses
