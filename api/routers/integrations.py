"""Settings for NGO admins: connect Google Calendar, see what is live, and see what the learned scoring knows so far.
Also the learning plans for staff and students."""
from __future__ import annotations

from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse

from pydantic import BaseModel, ConfigDict, Field

from matcher import config, google_calendar, learn, plan_choices

from ..deps import log, state, student_or_404
from ..security import Session, admin_only, ngo_only, student_only

router = APIRouter()


@router.get("/api/integrations/google/start")
def google_start(sess: Session = Depends(admin_only)):
    try:
        url = google_calendar.start(sess.user.id)
    except google_calendar.GoogleError as e:
        return RedirectResponse(f"/ngo/settings?google_error={quote(str(e))}", status_code=303)
    return RedirectResponse(url, status_code=303)


@router.get("/api/integrations/google/callback")
def google_callback(oauth_state: str = Query(default="", alias="state", max_length=200), code: str = Query(default="", max_length=2000),
                    error: str = Query(default="", max_length=200), sess: Session = Depends(admin_only)):
    if error or not code:
        return RedirectResponse(f"/ngo/settings?google_error={quote(error or 'Google sign-in was cancelled.')}", status_code=303)
    try:
        email = google_calendar.finish(oauth_state, code, sess.user.id, sess.user.username)
    except google_calendar.GoogleError as e:
        return RedirectResponse(f"/ngo/settings?google_error={quote(str(e))}", status_code=303)
    log("integration.google_connected", sess)
    return RedirectResponse(f"/ngo/settings?google=connected&account={quote(email)}", status_code=303)


@router.post("/api/integrations/google/disconnect")
def google_disconnect(sess: Session = Depends(admin_only)):
    google_calendar.disconnect()
    log("integration.google_disconnected", sess)
    return {"ok": True}


@router.get("/api/scoring")
def scoring(_: Session = Depends(ngo_only)):
    """What the live score is made of, and whether the learned part has enough to learn from."""
    st = state()
    return {"v2": dict(config.V2), "v3": dict(config.V3),
            "caps": {"upskill": config.UPSKILL_MAX, "ml": config.ML_MAX, "standing": config.STANDING_MAX,
                     "standing_min_field": config.STANDING_MIN_FIELD},
            "ml": learn.describe(st.ctx.model if st.ctx else None, st.labels)}  # type: ignore[arg-type]


@router.get("/api/students/{sid}/plan")
def student_plan(sid: str, _: Session = Depends(ngo_only)):
    """The plan the student sees: their own picks if they made any, else the suggested one."""
    return student_or_404(sid).plan(sid, plan_choices.get(sid))


@router.get("/api/me/plan")
def my_plan(sess: Session = Depends(student_only)):
    sid = sess.user.student_id or ""
    return state().plan(sid, plan_choices.get(sid))


class PlanPicks(BaseModel):
    model_config = ConfigDict(extra="forbid")
    opp_ids: list[str] = Field(max_length=plan_choices.MAX_CHOICES)


def _checked(sid: str, ids: list[str]) -> list[str]:
    """Only courses and mentors this student can take that teach something their best jobs ask for."""
    allowed = {o["opp_id"] for o in state().plan(sid)["options"]}
    bad = [i for i in ids if i not in allowed]
    if bad:
        raise HTTPException(422, "Some of these are not courses or mentors that fit your plan: " + ", ".join(bad[:5]))
    return list(dict.fromkeys(ids))


@router.post("/api/me/plan/preview")
def preview_plan(body: PlanPicks, sess: Session = Depends(student_only)):
    """What a set of picks would do, without saving anything. Real matches never change."""
    sid = sess.user.student_id or ""
    return state().plan(sid, _checked(sid, body.opp_ids))


@router.put("/api/me/plan/choices")
def save_plan(body: PlanPicks, sess: Session = Depends(student_only)):
    sid = sess.user.student_id or ""
    ids = _checked(sid, body.opp_ids)
    plan_choices.save(sid, ids)
    log("plan.chosen", sess, target=sid, detail=f"{len(ids)} picked")
    return state().plan(sid, ids or None)


@router.delete("/api/me/plan/choices")
def reset_plan(sess: Session = Depends(student_only)):
    sid = sess.user.student_id or ""
    plan_choices.save(sid, [])
    log("plan.reset", sess, target=sid)
    return state().plan(sid)
