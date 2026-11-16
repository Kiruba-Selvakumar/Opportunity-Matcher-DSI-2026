"""Employer leads from WhatsApp: read, reply, and map each one to a listing (or dismiss it). NGO admins only."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from matcher import leads, whatsapp

from ..deps import log, state
from ..security import Session, admin_only

router = APIRouter()


def _thread_or_404(lead_id: int) -> dict:
    t = leads.get_thread(lead_id)
    if t is None:
        raise HTTPException(404, "Not found.")
    return t


@router.get("/api/leads")
def lead_list(status: str | None = None, _: Session = Depends(admin_only)):
    if status and status not in leads.STATUSES:
        raise HTTPException(422, "Unknown status.")
    return leads.list_threads(status)


@router.get("/api/leads/unread")
def lead_unread(_: Session = Depends(admin_only)):
    return {"unread": leads.unread_total()}


@router.get("/api/leads/{lead_id}")
def lead_detail(lead_id: int, sess: Session = Depends(admin_only)):
    t = _thread_or_404(lead_id)
    log("lead.view", sess, target=str(lead_id))
    return t


@router.get("/api/leads/{lead_id}/suggest")
def lead_suggest(lead_id: int, _: Session = Depends(admin_only)):
    """A listing form pre-filled from everything the employer wrote."""
    t = _thread_or_404(lead_id)
    text = "\n".join(m["body"] for m in t["messages"] if m["direction"] == "in")
    return {**leads.suggest_listing(text, t["profile_name"]), "lead_id": lead_id}


class ReplyIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(min_length=1, max_length=1000)


@router.post("/api/leads/{lead_id}/reply")
def lead_reply(lead_id: int, body: ReplyIn, sess: Session = Depends(admin_only)):
    t = _thread_or_404(lead_id)
    oid = whatsapp.send_text(t["phone"], body.text.strip(), kind="lead_reply", recipient=f"lead:{lead_id}")
    leads.record_outgoing(lead_id, body.text.strip(), sess.user.username)
    log("lead.replied", sess, target=str(lead_id))
    return {"outbox_id": oid, "thread": leads.get_thread(lead_id)}


class LeadStatusIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: str = Field(max_length=10)
    note: str | None = Field(default=None, max_length=300)
    opp_id: str | None = Field(default=None, max_length=20)


@router.post("/api/leads/{lead_id}/status")
def lead_status(lead_id: int, body: LeadStatusIn, sess: Session = Depends(admin_only)):
    _thread_or_404(lead_id)
    if body.opp_id and body.opp_id not in state().opps:
        raise HTTPException(422, "That listing is not live.")
    try:
        leads.set_status(lead_id, body.status, sess.user.username, mapped_opp_id=body.opp_id, note=body.note)
    except ValueError as e:
        raise HTTPException(422, str(e))
    log("lead.status", sess, target=str(lead_id), detail=body.status)
    return leads.get_thread(lead_id)
