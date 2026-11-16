"""A student asks for a new mobile number; NGO staff approve or reject it before anything uses it.

The audit log records that a change was asked for and decided, never the number. Students only ever see their own
number masked; staff see a requested number in full so they can check it.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from matcher import contacts, notifications
from matcher.privacy import redact

from ..deps import log, state, tell
from ..security import Session, ngo_only, student_only

router = APIRouter()


class ChangeIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    phone: str = Field(min_length=1, max_length=20)


class DecisionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    approve: bool
    note: str = Field(default="", max_length=300)


def my_view(sid: str) -> dict:
    p, done = contacts.pending(sid), contacts.last_decided(sid)
    return {"phone": contacts.masked(contacts.phone(sid)),
            "pending": {"phone": contacts.masked(p["phone"]), "requested_at": p["requested_at"]} if p else None,
            "last": {"status": done["status"], "decided_at": done["decided_at"], "note": done["note"]} if done else None}


def staff_view(r: dict) -> dict:
    st = state()
    return {"id": r["id"], "student_id": r["student_id"], "name": st.contacts.get(r["student_id"]),
            "phone": r["phone"], "current": contacts.masked(contacts.phone(r["student_id"])), "requested_at": r["requested_at"]}


@router.get("/api/me/contact")
def my_contact(sess: Session = Depends(student_only)):
    return my_view(sess.user.student_id or "")


@router.post("/api/me/contact-change")
def ask_for_change(body: ChangeIn, sess: Session = Depends(student_only)):
    sid = sess.user.student_id or ""
    try:
        contacts.request_change(sid, body.phone)
    except contacts.ContactError as e:
        raise HTTPException(422, str(e))
    log("contact.change_requested", sess, target=sid)
    tell(notifications.ngo_user_ids(), "review", "A student asked to change their mobile number.", f"/ngo/students/{sid}")
    return my_view(sid)


@router.get("/api/contact-changes")
def waiting_changes(student_id: str | None = None, _: Session = Depends(ngo_only)):
    rows = contacts.all_pending()
    return [staff_view(r) for r in rows if student_id in (None, r["student_id"])]


@router.post("/api/contact-changes/{change_id}/decision")
def decide_change(change_id: int, body: DecisionIn, sess: Session = Depends(ngo_only)):
    note = redact(body.note, list(state().contacts.values()))       # the note reaches the student: no numbers or names in it
    try:
        row = contacts.decide(change_id, body.approve, sess.user.username, note)
    except contacts.ContactError as e:
        raise HTTPException(404, str(e))
    sid = row["student_id"]
    log("contact.change_decided", sess, target=sid, detail=row["status"])
    tell(notifications.student_user_id(sid), "account",
         "Your new mobile number is now in use." if body.approve
         else "The NGO did not change your mobile number." + (f" {row['note']}" if row["note"] else ""), "/student/profile")
    return {"id": row["id"], "status": row["status"]}
