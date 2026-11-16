"""Bulk WhatsApp, consent, the outbox, and the WhatsApp webhook.

Admins plan and send broadcasts. Staff and students record WhatsApp consent. Meta calls the webhook: a message from a
student's number lands in that student's thread, anything else becomes an employer lead for the admins.
"""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, ConfigDict, Field

from matcher import audit, broadcast, chat, config, contacts, integrations, leads, notifications, outbox, settings, standins, whatsapp

from ..deps import log, state, student_or_404, tell
from ..security import Session, admin_only, ngo_only, student_only

router = APIRouter()


# ---------------- outbox and integrations ----------------

@router.get("/api/outbox")
def outbox_list(channel: str | None = None, batch: str | None = None, limit: int = 200, _: Session = Depends(admin_only)):
    if channel and channel not in ("email", "whatsapp"):
        raise HTTPException(422, "Unknown channel.")
    return outbox.list_items(channel=channel, batch_id=batch, limit=limit)


@router.get("/api/integrations")
def integration_status(_: Session = Depends(admin_only)):
    return integrations.status()


# ---------------- broadcasts ----------------

class BroadcastIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: str = Field(max_length=20)
    opp_id: str | None = Field(default=None, max_length=20)
    program: str | None = Field(default=None, max_length=20)
    branch: str | None = Field(default=None, max_length=40)
    text: str = Field(default="", max_length=broadcast.MAX_TEXT + 50)
    min_score: float = Field(default=config.MIN_SHOW_SCORE, ge=0, le=1)
    limit: int = Field(default=200, ge=1, le=1000)


def _plan(body: BroadcastIn) -> dict:
    st = state()
    opp = st.opps.get(body.opp_id) if body.opp_id else None
    if body.kind == "opportunity" and opp is None:
        raise HTTPException(404, "That listing is not live.")
    try:
        return broadcast.plan(body.kind, st.students, rows_for_opp=st.rows_by_opp.get(body.opp_id) if body.opp_id else None, opp=opp,
                              matches_of=st.matches, program=body.program or None, branch=body.branch or None, text=body.text,
                              min_score=body.min_score, limit=body.limit, known_names=list(st.contacts.values()))
    except ValueError as e:
        raise HTTPException(422, str(e))


@router.post("/api/broadcasts/preview")
def broadcast_preview(body: BroadcastIn, _: Session = Depends(admin_only)):
    p = _plan(body)
    return {k: v for k, v in p.items() if k != "recipients"}


@router.post("/api/broadcasts")
def broadcast_send(body: BroadcastIn, sess: Session = Depends(admin_only)):
    p = _plan(body)
    if not p["reachable"]:
        raise HTTPException(422, "Nobody in this group has agreed to WhatsApp messages yet.")
    res = broadcast.send(p)
    log("broadcast.sent", sess, target=body.opp_id or body.kind, detail=f"{res['queued']} queued, batch {res['batch_id']}")
    return {**res, "total": p["total"], "not_agreed": p["not_agreed"], "no_phone": p["no_phone"]}


# ---------------- consent ----------------

class ConsentIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    whatsapp: bool


@router.get("/api/students/{sid}/consent")
def student_consent(sid: str, _: Session = Depends(ngo_only)):
    student_or_404(sid)
    return contacts.consent(sid)


@router.put("/api/students/{sid}/consent")
def set_student_consent(sid: str, body: ConsentIn, sess: Session = Depends(ngo_only)):
    """Staff record what the student told them (for example on a call). The audit log keeps who recorded it."""
    student_or_404(sid)
    contacts.set_opt_in(sid, body.whatsapp, f"staff:{sess.user.username}")
    log("consent.whatsapp", sess, target=sid, detail="yes" if body.whatsapp else "no")
    return contacts.consent(sid)


@router.get("/api/me/consent")
def my_consent(sess: Session = Depends(student_only)):
    return contacts.consent(sess.user.student_id or "")


@router.put("/api/me/consent")
def set_my_consent(body: ConsentIn, sess: Session = Depends(student_only)):
    sid = sess.user.student_id or ""
    contacts.set_opt_in(sid, body.whatsapp, "student")
    log("consent.whatsapp", sess, target=sid, detail="yes" if body.whatsapp else "no")
    return contacts.consent(sid)


# ---------------- WhatsApp webhook (called by Meta, not by a signed-in person) ----------------

@router.get("/api/whatsapp/webhook")
def whatsapp_verify(request: Request):
    q = request.query_params
    token = settings.whatsapp_verify_token()
    if token and q.get("hub.mode") == "subscribe" and q.get("hub.verify_token") == token:
        return PlainTextResponse(q.get("hub.challenge", ""))
    raise HTTPException(403, "Not allowed.")


@router.post("/api/whatsapp/webhook")
async def whatsapp_incoming(request: Request):
    raw = await request.body()
    secret = settings.whatsapp_app_secret()
    if secret:
        if not whatsapp.verify_signature(raw, request.headers.get("x-hub-signature-256"), secret):
            audit.record("whatsapp.bad_signature", ip=request.client.host if request.client else None)
            raise HTTPException(403, "Not allowed.")
    elif settings.cookie_secure():
        raise HTTPException(403, "Not allowed.")       # never accept unsigned calls in production
    try:
        payload = json.loads(raw or b"{}")
    except ValueError:
        raise HTTPException(400, "Bad request.")
    messages, statuses = whatsapp.parse_webhook(payload)
    for s in statuses:
        if s["id"]:
            outbox.update_by_provider_id(s["id"], s["status"] if s["status"] in outbox.ORDER or s["status"] == "failed" else "sent", s["error"])
    new_leads = 0
    st = state() if messages else None
    for m in messages:
        sid = standins.incoming_student(m["from"])
        if sid and st and sid in st.students:
            try:
                chat.post_message(chat.Message(thread_type="student", thread_id=sid, sender_role="student", body=m["text"][:chat.MAX_LEN]),
                                  known_names=list(st.contacts.values()))
                tell(notifications.ngo_user_ids(), "message", "A student replied on WhatsApp.", f"/ngo/messages?thread=student:{sid}")
            except ValueError:
                pass
        else:
            thread = leads.record_incoming(m["from"], m["text"], m["id"], m.get("name"))
            if thread is not None:
                new_leads += 1
                if leads.is_first_message(thread):             # the first time they write, ask for what a listing needs
                    whatsapp.send_text(m["from"], leads.AUTO_REPLY, kind="lead_auto", recipient=f"lead:{thread}")
                    leads.record_outgoing(thread, leads.AUTO_REPLY, "automatic reply")
    if new_leads:
        tell(notifications.admin_user_ids(), "lead", "A new WhatsApp message from an employer is waiting.", "/ngo/messages?tab=leads")
    return {"ok": True}
