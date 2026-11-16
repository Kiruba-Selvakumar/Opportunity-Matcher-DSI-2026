"""NGO case work: notes, follow-ups, the timeline for one student, and the dashboard."""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from matcher import applications, casework, chat, contacts, interviews, leads, listings, resumes
from matcher.rank import top_k

from .. import helpers
from ..deps import log, state, student_or_404
from ..security import Session, ngo_only
from .applications import title_of

router = APIRouter()


class NoteIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    body: str = Field(max_length=casework.MAX_NOTE + 100)
    follow_up_on: str | None = Field(default=None, max_length=10)


@router.get("/api/students/{sid}/notes")
def list_notes(sid: str, _: Session = Depends(ngo_only)):
    student_or_404(sid)
    return casework.list_notes(sid)


@router.post("/api/students/{sid}/notes")
def add_note(sid: str, body: NoteIn, sess: Session = Depends(ngo_only)):
    st = student_or_404(sid)
    try:
        n = casework.add_note(sid, sess.user.username, body.body, body.follow_up_on, known_names=list(st.contacts.values()))
    except ValueError as e:
        raise HTTPException(422, str(e))
    log("note.added", sess, target=sid, detail="with follow-up" if body.follow_up_on else None)
    return n


@router.post("/api/notes/{note_id}/done")
def note_done(note_id: int, sess: Session = Depends(ngo_only)):
    if not casework.mark_done(note_id):
        raise HTTPException(404, "Not found.")
    log("note.done", sess, target=str(note_id))
    return {"ok": True}


@router.get("/api/students/{sid}/timeline")
def timeline(sid: str, _: Session = Depends(ngo_only)):
    st = student_or_404(sid)
    titles = {oid: title_of(st, oid) for oid in {a["opp_id"] for a in applications.list_apps(student_id=sid)} | set(st.opps)}
    return casework.timeline(sid, titles, edited_at=st.edits.get(sid, {}).get("_updated_at"))


@router.get("/api/followups")
def followups(_: Session = Depends(ngo_only)):
    return casework.due_followups()


@router.get("/api/dashboard")
def dashboard(_: Session = Depends(ngo_only)):
    st = state()
    apps = applications.list_apps()
    n_status = lambda s: sum(1 for a in apps if a["status"] == s)  # noqa: E731
    no_match = [sid for sid, rows in st.rows_by_student.items() if not top_k(rows)]
    missing = sorted(((len(s.missing_fields), sid) for sid, s in st.students.items() if s.missing_fields), reverse=True)
    stale = [a for a in apps if a["status"] in ("shared", "shortlisted", "interview", "offered") and a["days_in_stage"] >= 7]
    busiest = sorted(((n, oid) for oid, n in st.ctx.load.items() if oid in st.opps), reverse=True)[:5]  # type: ignore[union-attr]
    due = casework.due_followups()
    waiting = [a for a in apps if a["status"] == "interested"]
    soon = [iv for iv in interviews.list_for(upcoming=True) if (date.fromisoformat(iv["starts_at"][:10]) - date.today()).days <= 7]
    closing = sorted((o.apply_by, oid) for oid, o in st.opps.items() if helpers.closing_soon(o.apply_by))
    with_cv = sum(1 for sid in resumes.all_meta() if sid in st.students)
    return {
        "counts": {"students": len(st.students), "active_listings": len(st.opps),
                   "pending_reviews": len(listings.list_all("pending")), "interests_waiting": n_status("interested"),
                   "unread_messages": chat.unread_total(), "hired": n_status("hired"), "in_play": sum(st.ctx.load.values()),  # type: ignore[union-attr]
                   "put_forward": sum(1 for a in waiting if a.get("recommended_by")), "interviews_week": len(soon),
                   "closing_soon": len(closing), "new_leads": leads.unread_total(), "with_resume": with_cv,
                   "number_changes": len(contacts.all_pending())},
        "funnel": applications.funnel(),
        "attention": {
            "number_changes": sorted({r["student_id"] for r in contacts.all_pending()}),
            "no_matches": {"count": len(no_match), "ids": no_match[:10]},
            "missing_info": {"count": len(missing), "items": [{"id": sid, "missing": n} for n, sid in missing[:8]]},
            "stale": [{"id": a["id"], "student_id": a["student_id"], "title": title_of(st, a["opp_id"]), "status": a["status"],
                       "days": a["days_in_stage"]} for a in stale[:8]],
            "busiest": [{"opp_id": oid, "title": title_of(st, oid), "load": n, "openings": st.opps[oid].openings} for n, oid in busiest],
            "followups": [{"id": n["id"], "student_id": n["student_id"], "due": n["follow_up_on"], "text": n["body"][:80]} for n in due[:8]],
            "interviews": [{"id": iv["id"], "student_id": iv["student_id"], "title": title_of(st, iv["opp_id"]),
                            "when": interviews.words(iv["starts_at"]), "mode": iv["mode"], "interviewer": iv["interviewer"]} for iv in soon[:8]],
            "closing": [{"opp_id": oid, "title": st.opps[oid].title, "apply_by": d,
                         "eligible": sum(r.eligible for r in st.rows_by_opp[oid])} for d, oid in closing[:8]],
        },
    }
