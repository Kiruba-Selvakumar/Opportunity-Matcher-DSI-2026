"""Interview scheduling for NGO staff and employers, the notes afterwards, and the Fireflies webhook.

The employer or the NGO can take an interview. Either can schedule it once the student is shortlisted (the NGO also from
"shared"). Scheduling moves the application to the interview stage. Students see the time and the link in Applications.
"""
from __future__ import annotations

import json
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from matcher import (accounts, applications, audit, casework, fireflies, google_calendar, interviews, meetings,
                     notifications, settings)
from matcher.applications import ApplicationError
from matcher.privacy import candidate_code

from .. import helpers
from ..deps import log, state, tell
from ..security import Session, employer_only, get_session, ngo_only
from .applications import title_of

router = APIRouter()
NGO_FROM = ("shared", "shortlisted", "interview")
EMPLOYER_FROM = ("shortlisted", "interview")


class InterviewIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    starts_at: str = Field(max_length=32)
    minutes: int = Field(default=30, ge=10, le=240)
    interviewer: str = Field(default="employer", max_length=10)
    interviewer_email: str | None = Field(default=None, max_length=254)
    mode: str = Field(default="meet", max_length=10)
    location: str | None = Field(default=None, max_length=200)
    meet_link: str | None = Field(default=None, max_length=300)
    notetaker: bool = False
    invite_student: bool = False


def _owner_emails(oid: str) -> list[str]:
    return accounts.emails_of(notifications.owner_user_ids(oid))


def _code(sid: str) -> str:
    return candidate_code(sid, settings.candidate_salt())


def _schedule(sess: Session, app_id: int, body: InterviewIn, role: str) -> dict:
    st = state()
    a = applications.get(app_id)
    if a is None:
        raise HTTPException(404, "Not found.")
    if role == "lister":
        if a["opp_id"] not in sess.user.listings or app_id not in applications.shared_ids(a["opp_id"]):
            raise HTTPException(404, "Not found.")
        if a["status"] not in EMPLOYER_FROM:
            raise HTTPException(422, "Shortlist the candidate first, then schedule the interview.")
        body.interviewer = "employer"
    elif a["status"] not in NGO_FROM:
        raise HTTPException(422, "Share the student with the employer first, then schedule the interview.")
    if body.interviewer not in interviews.INTERVIEWERS:
        raise HTTPException(422, "Say who takes the interview: the employer or the NGO.")
    owners = _owner_emails(a["opp_id"])
    email = body.interviewer_email or (sess.user.email if (role == "lister" or body.interviewer == "ngo") else (owners[0] if owners else None))
    try:                                   # check before moving the application, so a refused interview leaves it as it was
        interviews.check(body.starts_at, body.minutes, body.interviewer, interviewer_email=email, mode=body.mode,
                         location=body.location, meet_link=body.meet_link)
    except interviews.InterviewError as e:
        raise HTTPException(422, str(e))
    if a["status"] != "interview":
        try:
            applications.transition(app_id, "interview", role, sess.user.id, "Interview scheduled.")
        except ApplicationError as e:
            raise HTTPException(422, str(e))
        st.refresh_load()
    title = title_of(st, a["opp_id"])
    try:
        res = meetings.schedule(applications.get(app_id), title, _code(a["student_id"]), sess.user.username, starts_at=body.starts_at,  # type: ignore[arg-type]
                                minutes=body.minutes, interviewer=body.interviewer, interviewer_email=email, mode=body.mode,
                                location=body.location, meet_link=body.meet_link, notetaker=body.notetaker,
                                invite_student=body.invite_student and role != "lister", employer_emails=owners)
    except interviews.InterviewError as e:
        raise HTTPException(422, str(e))
    iv = res["interview"]
    log("interview.scheduled", sess, target=f"{a['student_id']}/{a['opp_id']}", detail=f"{iv['mode']} via {res['calendar']}")
    when = interviews.words(iv["starts_at"])
    tell(notifications.student_user_id(a["student_id"]), "application", f"Interview for “{title}” on {when}.", "/student/applications")
    if role == "lister":
        tell(notifications.ngo_user_ids(), "application", f"The employer scheduled an interview for “{title}” on {when}.", "/ngo/applications?tab=interviews")
    else:
        tell(notifications.owner_user_ids(a["opp_id"]), "application", f"The NGO scheduled an interview for “{title}” on {when}.", f"/employer/{a['opp_id']}")
    return {"interview": helpers.interview_view(iv, "ngo" if role == "ngo" else "employer"), "calendar": res["calendar"], "warnings": res["warnings"]}


@router.post("/api/applications/{app_id}/interviews")
def ngo_schedule(app_id: int, body: InterviewIn, sess: Session = Depends(ngo_only)):
    return _schedule(sess, app_id, body, "ngo")


@router.post("/api/me/applications/{app_id}/interviews")
def employer_schedule(app_id: int, body: InterviewIn, sess: Session = Depends(employer_only)):
    return _schedule(sess, app_id, body, "lister")


def _interview_for(sess: Session, iid: int) -> tuple[dict, str]:
    """The interview and the caller's side ("ngo" or "employer"). Anyone else gets "not found"."""
    iv = interviews.get(iid)
    if iv is None:
        raise HTTPException(404, "Not found.")
    if sess.user.is_ngo:
        return iv, "ngo"
    if sess.user.role == "employer" and iv["opp_id"] in sess.user.listings:
        return iv, "employer"
    raise HTTPException(404, "Not found.")


@router.get("/api/interviews")
def ngo_interviews(upcoming: bool = True, _: Session = Depends(ngo_only)):
    st = state()
    return [{**helpers.interview_view(iv, "ngo"), "title": title_of(st, iv["opp_id"]), "candidate_code": _code(iv["student_id"])}
            for iv in interviews.list_for(upcoming=upcoming)]


@router.get("/api/me/interviews")
def employer_interviews(sess: Session = Depends(employer_only)):
    st = state()
    return [{**helpers.interview_view(iv, "employer"), "title": title_of(st, iv["opp_id"]), "candidate_code": _code(iv["student_id"])}
            for iv in interviews.list_for(opp_ids=list(sess.user.listings), upcoming=True)]


class InterviewPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    starts_at: str | None = Field(default=None, max_length=32)
    minutes: int | None = Field(default=None, ge=10, le=240)
    status: str | None = Field(default=None, max_length=12)


@router.patch("/api/interviews/{iid}")
def change_interview(iid: int, body: InterviewPatch, sess: Session = Depends(get_session)):
    iv, side = _interview_for(sess, iid)
    if iv["status"] == "cancelled":        # its calendar event is gone and everyone was told, so it cannot come back
        raise HTTPException(422, "This interview was cancelled. Schedule a new one instead.")
    st = state()
    title, code, owners = title_of(st, iv["opp_id"]), _code(iv["student_id"]), _owner_emails(iv["opp_id"])
    try:
        if body.status == "cancelled":
            iv = meetings.cancel(iv, title, owners, code)
            tell(notifications.student_user_id(iv["student_id"]), "application", f"The interview for “{title}” was cancelled.", "/student/applications")
        elif body.starts_at:
            iv = meetings.reschedule(iv, title, body.starts_at, body.minutes or iv["minutes"], owners, code)
            tell(notifications.student_user_id(iv["student_id"]), "application",
                 f"The interview for “{title}” moved to {interviews.words(iv['starts_at'])}.", "/student/applications")
        elif body.status in ("done", "no_show", "scheduled"):
            iv = interviews.update(iid, status=body.status)
        else:
            raise HTTPException(422, "Say what to change: a new time, or a status.")
    except (interviews.InterviewError, google_calendar.GoogleError) as e:
        raise HTTPException(422, str(e))
    log("interview.changed", sess, target=str(iid), detail=body.status or "moved")
    return helpers.interview_view(iv, side)


class NotesIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(min_length=1, max_length=30000)


@router.post("/api/interviews/{iid}/notes")
def paste_notes(iid: int, body: NotesIn, sess: Session = Depends(get_session)):
    iv, side = _interview_for(sess, iid)
    try:
        iv = meetings.paste_notes(iv, body.text, list(state().contacts.values()))
    except ValueError as e:
        raise HTTPException(422, str(e))
    log("interview.notes", sess, target=str(iid), detail="pasted")
    return helpers.interview_view(iv, side)


@router.post("/api/interviews/{iid}/fetch-notes")
def fetch_notes(iid: int, sess: Session = Depends(ngo_only)):
    iv, _ = _interview_for(sess, iid)
    try:
        got = meetings.fetch_notes(iv, list(state().contacts.values()))
    except fireflies.FirefliesError as e:
        raise HTTPException(422, str(e))
    if got is None:
        raise HTTPException(404, "Fireflies has no transcript for this interview yet. It is usually ready a few minutes after the call ends.")
    log("interview.notes", sess, target=str(iid), detail="fireflies")
    return helpers.interview_view(got, "ngo")


@router.post("/api/interviews/{iid}/notetaker")
def notetaker_now(iid: int, sess: Session = Depends(ngo_only)):
    iv, _ = _interview_for(sess, iid)
    try:
        ok = meetings.send_notetaker_now(iv, title_of(state(), iv["opp_id"]))
    except fireflies.FirefliesError as e:
        raise HTTPException(422, str(e))
    log("interview.notetaker", sess, target=str(iid))
    return {"ok": ok}


class ToNotesIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    follow_up_on: str | None = Field(default=None, max_length=10)


@router.post("/api/interviews/{iid}/to-case-notes")
def actions_to_case_notes(iid: int, body: ToNotesIn, sess: Session = Depends(ngo_only)):
    """Copy the action points into the student's case notes, with an optional follow-up date."""
    iv, _ = _interview_for(sess, iid)
    if not iv["action_items"]:
        raise HTTPException(422, "There are no action points yet.")
    st = state()
    text = f"Interview for {title_of(st, iv['opp_id'])}: action points\n" + "\n".join(f"- {a}" for a in iv["action_items"])
    try:
        n = casework.add_note(iv["student_id"], sess.user.username, text[:casework.MAX_NOTE], body.follow_up_on,
                              known_names=list(st.contacts.values()))
    except ValueError as e:
        raise HTTPException(422, str(e))
    log("note.added", sess, target=iv["student_id"], detail="from interview")
    return n


@router.get("/api/interviews/{iid}/invite.ics")
def interview_ics(iid: int, sess: Session = Depends(get_session)):
    from datetime import datetime

    from matcher import ics
    iv, _ = _interview_for(sess, iid)
    title = title_of(state(), iv["opp_id"])
    data = ics.event(f"interview-{iid}@opportunity-matcher", datetime.fromisoformat(iv["starts_at"]), iv["minutes"],
                     f"Interview: {title} ({interviews.tag(iid)})", f"Candidate {_code(iv['student_id'])}",
                     iv["meet_link"] or iv["location"] or "", sequence=iv["sequence"], cancelled=iv["status"] == "cancelled")
    return Response(data, media_type="text/calendar", headers={"Content-Disposition": f'attachment; filename="interview-{iid}.ics"'})


# ---------------- Fireflies webhook (called by Fireflies, not by a signed-in person) ----------------

@router.post("/api/fireflies/webhook")
async def fireflies_done(request: Request):
    raw = await request.body()
    cfg = settings.fireflies()
    secret = cfg["webhook_secret"] if cfg else ""
    if secret:
        if not fireflies.verify_signature(raw, request.headers.get("x-hub-signature"), secret):
            audit.record("fireflies.bad_signature", ip=request.client.host if request.client else None)
            raise HTTPException(403, "Not allowed.")
    elif settings.cookie_secure() or cfg is None:
        raise HTTPException(403, "Not allowed.")
    try:
        payload = json.loads(raw or b"{}")
    except ValueError:
        raise HTTPException(400, "Bad request.")
    mid = payload.get("meetingId")
    if not mid:
        return {"ok": True, "matched": False}
    try:
        t = fireflies.transcript(str(mid))
    except fireflies.FirefliesError:
        raise HTTPException(502, "Fireflies could not be reached.")
    iv = meetings.save_transcript(t, list(state().contacts.values())) if t else None
    if iv:
        audit.record("interview.notes", target=str(iv["id"]), detail="fireflies webhook")
        tell(notifications.ngo_user_ids(), "application", f"Notes are ready for an interview on {date.fromisoformat(iv['starts_at'][:10]):%d %b}.",
             "/ngo/applications?tab=interviews")
    return {"ok": True, "matched": iv is not None}
