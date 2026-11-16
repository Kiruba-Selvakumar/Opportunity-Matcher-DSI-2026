"""A student's own profile: edit circumstances, add skills from a resume PDF, download their data."""
from __future__ import annotations

import hashlib
import json
from typing import Literal

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile
from pydantic import ValidationError

from matcher import applications, chat, export_html, profile_edits, resume_pdf, resumes
from matcher.parse_text import extract_resume
from matcher.profile_edits import ProfileEdit
from matcher.skills import normalize

from .. import helpers
from ..deps import log, state
from ..security import Session, get_session, student_only
from .applications import student_view

router = APIRouter()


def payload(st: helpers.State, sid: str) -> dict:
    s = st.students[sid]
    skills = st.norm["students"][sid]["skills"]
    e = st.edits.get(sid, {})
    return {"profile": helpers.student_profile(st, sid), "completeness": profile_edits.completeness(s, skills, st.rows_by_student[sid]),
            "edited_fields": profile_edits.edited_fields(e), "edited_at": e.get("_updated_at"),
            "extra_skills": e.get("extra_skills", [])}


@router.get("/api/skills")
def skill_list(_: Session = Depends(get_session)):
    return state().vocab


@router.get("/api/me/profile")
def my_profile(sess: Session = Depends(student_only)):
    return payload(state(), sess.user.student_id or "")


@router.put("/api/me/profile")
def edit_profile(body: ProfileEdit, sess: Session = Depends(student_only)):
    st, sid = state(), sess.user.student_id or ""
    try:
        profile_edits.save_edits(sid, body, user_id=sess.user.id)
    except ValueError as e:
        raise HTTPException(422, str(e))
    st.refresh_student(sid)
    log("profile.updated", sess, target=sid, detail=",".join(sorted(body.model_fields_set)))
    return payload(st, sid)


@router.post("/api/me/resume")
async def read_resume(file: UploadFile = File(...), keep: bool = False, sess: Session = Depends(student_only)):
    """Read a resume PDF and suggest skills. Nothing is added until the student picks them.
    With keep=true the file is also stored as the student's resume, so the NGO can read it and it gets an ATS score."""
    st, sid = state(), sess.user.student_id or ""
    data = await file.read(resume_pdf.MAX_BYTES + 1)
    try:
        text, pages = resume_pdf.pdf_to_text(data)
        saved = resumes.save(sid, data, "student", sess.user.username) if keep else None
    except resume_pdf.ResumeError as e:
        raise HTTPException(422, str(e))
    found = extract_resume(text)
    skills, _ = normalize(found["skills_raw"])
    have = set(st.norm["students"][sid]["skills"])
    log("resume.saved" if keep else "resume.read", sess, target=sid, detail=f"sha256:{hashlib.sha256(data).hexdigest()[:12]} bytes:{len(data)}")
    return {"suggested": [s for s in skills if s not in have], "already": [s for s in skills if s in have], "pages": pages,
            "resume": helpers.resume_summary(saved, st.norm["students"][sid]["skills"]) if saved else None}


@router.get("/api/me/export")
def export_my_data(format: Literal["json", "html"] = "json", sess: Session = Depends(student_only)):
    st, sid = state(), sess.user.student_id or ""
    out = {
        "account": {"username": sess.user.username, "display_name": sess.user.display_name},
        "name": st.contacts.get(sid), **payload(st, sid),
        "applications": [student_view(st, a) for a in applications.list_apps(student_id=sid)],
        "saved": applications.saved(sid),
        "resume": helpers.resume_summary(resumes.meta(sid)),
        "messages": [{"at": m.created_at, "from": m.sender_role, "about": m.about_opp_id, "text": m.body}
                     for m in chat.list_messages("student", sid)],
    }
    log("export.downloaded", sess, target=sid, detail=f"format:{format}")
    if format == "html":
        ids = set(out["saved"]) | {m["about"] for m in out["messages"] if m["about"]}
        titles = {o: (st.opps[o].title, st.opps[o].org_name) for o in ids if o in st.opps}
        return Response(export_html.render(out, titles), media_type="text/html; charset=utf-8",
                        headers={"Content-Disposition": "attachment; filename=my-data.html"})
    return Response(json.dumps(out, indent=2), media_type="application/json",
                    headers={"Content-Disposition": "attachment; filename=my-data.json"})
