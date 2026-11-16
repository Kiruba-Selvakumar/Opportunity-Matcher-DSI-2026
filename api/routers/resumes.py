"""Resumes: NGO upload (one or many at once), the viewer, ATS scores, and a student's own resume.

Files never go to employers or an LLM. Every time someone opens a resume, the audit log records who and whose.
"""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field

from matcher import resume_pdf, resumes, settings
from matcher.privacy import candidate_code

from .. import helpers
from ..deps import log, state, student_or_404
from ..security import Session, admin_only, ngo_only, student_only

router = APIRouter()
MAX_FILES = 25


async def _read(file: UploadFile) -> bytes:
    data = await file.read(resume_pdf.MAX_BYTES + 1)
    if len(data) > resume_pdf.MAX_BYTES:
        raise resume_pdf.ResumeError("The file is larger than 5 MB.")
    return data


def _pdf(sid: str) -> FileResponse:
    f = resumes.file_for(sid)
    if resumes.meta(sid) is None or not f.exists():
        raise HTTPException(404, "There is no resume for this student yet.")
    return FileResponse(f, media_type="application/pdf", headers={"Content-Disposition": f'inline; filename="resume-{sid}.pdf"'})


# ---------------- NGO ----------------

@router.get("/api/resumes")
def resume_list(_: Session = Depends(ngo_only)):
    st = state()
    return {sid: {"score": m["quality"], "uploaded_at": m["uploaded_at"], "source": m["source"]}
            for sid, m in resumes.all_meta().items() if sid in st.students}


@router.get("/api/students/{sid}/resume")
def student_resume(sid: str, _: Session = Depends(ngo_only)):
    st = student_or_404(sid)
    return helpers.resume_summary(resumes.meta(sid), st.norm["students"][sid]["skills"])


@router.get("/api/students/{sid}/resume.pdf")
def student_resume_pdf(sid: str, sess: Session = Depends(ngo_only)):
    student_or_404(sid)
    log("resume.view", sess, target=sid)
    return _pdf(sid)


@router.get("/api/students/{sid}/resume/ats")
def student_resume_ats(sid: str, opp_id: str, _: Session = Depends(ngo_only)):
    st = student_or_404(sid)
    if opp_id not in st.opps:
        raise HTTPException(404, "Not found.")
    return helpers.ats_for(st, sid, opp_id)


@router.post("/api/students/{sid}/resume")
async def upload_student_resume(sid: str, file: UploadFile = File(...), sess: Session = Depends(ngo_only)):
    st = student_or_404(sid)
    try:
        m = resumes.save(sid, await _read(file), "ngo", sess.user.username)
    except resume_pdf.ResumeError as e:
        raise HTTPException(422, str(e))
    log("resume.saved", sess, target=sid, detail="by the NGO")
    return helpers.resume_summary(m, st.norm["students"][sid]["skills"])


@router.delete("/api/students/{sid}/resume")
def delete_student_resume(sid: str, sess: Session = Depends(admin_only)):
    student_or_404(sid)
    if not resumes.delete(sid):
        raise HTTPException(404, "There is no resume for this student.")
    log("resume.deleted", sess, target=sid)
    return {"ok": True}


class MatchNamesIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    filenames: list[str] = Field(max_length=MAX_FILES)


@router.post("/api/resumes/match")
def match_files(body: MatchNamesIn, _: Session = Depends(ngo_only)):
    """Which student each file is for, from its name. A student ID or candidate code is certain; a name is a suggestion."""
    st = state()
    salt = settings.candidate_salt()
    codes = {candidate_code(sid, salt): sid for sid in st.students}
    out = resumes.match_filenames([f[:200] for f in body.filenames], list(st.students), codes, st.contacts)
    have = resumes.all_meta()
    for x in out:
        x["replaces"] = bool(x["student_id"] and x["student_id"] in have)
    return out


@router.post("/api/resumes/bulk")
async def bulk_upload(files: list[UploadFile] = File(...), mapping: str = Form(..., max_length=20000),
                      sess: Session = Depends(ngo_only)):
    """Save many resumes at once. mapping is {"file name": "student ID"}; files left out or mapped to "" are skipped."""
    st = state()
    if len(files) > MAX_FILES:
        raise HTTPException(422, f"Upload at most {MAX_FILES} files at a time.")
    try:
        plan = json.loads(mapping)
        assert isinstance(plan, dict) and all(isinstance(k, str) and isinstance(v, str) for k, v in plan.items())
    except (ValueError, AssertionError):
        raise HTTPException(422, "The file-to-student list could not be read.")
    results = []
    for f in files:
        name = (f.filename or "")[:200]
        sid = plan.get(name, "")
        if not sid:
            results.append({"file": name, "student_id": None, "ok": False, "message": "Skipped: no student chosen."})
            continue
        if sid not in st.students:
            results.append({"file": name, "student_id": sid, "ok": False, "message": "There is no student with that ID."})
            continue
        try:
            m = resumes.save(sid, await _read(f), "bulk", sess.user.username)
            results.append({"file": name, "student_id": sid, "ok": True, "score": m["quality"], "message": "Saved."})
        except resume_pdf.ResumeError as e:
            results.append({"file": name, "student_id": sid, "ok": False, "message": str(e)})
    saved = [r["student_id"] for r in results if r["ok"]]
    log("resume.bulk", sess, detail=f"{len(saved)} saved of {len(files)}")
    return {"saved": len(saved), "results": results}


# ---------------- student ----------------

@router.get("/api/me/resume")
def my_resume(sess: Session = Depends(student_only)):
    st, sid = state(), sess.user.student_id or ""
    return helpers.resume_summary(resumes.meta(sid), st.norm["students"][sid]["skills"])


@router.get("/api/me/resume.pdf")
def my_resume_pdf(sess: Session = Depends(student_only)):
    return _pdf(sess.user.student_id or "")
