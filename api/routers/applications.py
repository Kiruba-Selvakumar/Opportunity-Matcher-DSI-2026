"""A student's interest in a listing and its journey. Students, NGO staff and employers each move it in their own way."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from matcher import applications, interviews, listings, mailer, notifications, resumes
from matcher.applications import ACTIVE, ApplicationError, EMPLOYER_STAGES, NEXT, WORDS
from matcher.privacy import candidate_code
from matcher import settings
from matcher.recommend import close_the_gap, fit_label

from .. import helpers
from ..deps import log, state, tell
from ..security import Session, employer_only, ngo_only, student_only

router = APIRouter()


class InterestIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    opp_id: str = Field(max_length=20)
    note: str = Field(default="", max_length=500)


class MoveIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: str = Field(max_length=20)
    note: str = Field(default="", max_length=500)


def title_of(st: helpers.State, oid: str) -> str:
    o = st.opps.get(oid) or st.pipeline_opps.get(oid)      # a listing past its last day has left matching, but still has a name
    if o:
        return o.title
    row = listings.get(oid)
    return row["data"]["title"] if row else oid


def student_view(st: helpers.State, a: dict, events: bool = True) -> dict:
    o = st.opps.get(a["opp_id"])
    row = listings.get(a["opp_id"])
    d = row["data"] if row else None
    out = {"id": a["id"], "opp_id": a["opp_id"], "title": title_of(st, a["opp_id"]),
           "org_name": o.org_name if o else (d["org_name"] if d else ""), "type": o.type if o else (d["type"] if d else "job"),
           "city": o.city if o else (d["city"] if d else ""), "status": a["status"], "words": a["words"],
           "student_note": a["student_note"], "ngo_note": a["ngo_note"],
           "employer_note": a["employer_note"] if a["status"] == "not_a_fit" else None,
           "days_in_stage": a["days_in_stage"], "created_at": a["created_at"],
           "can_withdraw": a["status"] in ACTIVE,
           # the NGO has put them forward and an admin is deciding whether to share; never says who
           "reviewing": a["status"] == "interested" and bool(a.get("recommended_by")),
           "interviews": [helpers.interview_view(i, "student") for i in interviews.list_for(application_id=a["id"])]}
    if a["status"] in ("declined", "not_a_fit", "withdrawn"):
        # where it ended, so the student's lifeline can stop at the right step
        ends = [e for e in applications.events(a["id"]) if e["to_status"] == a["status"]]
        out["stopped_at"] = ends[-1]["from_status"] if ends else None
    if events:
        out["events"] = [{"at": e["at"], "by": {"student": "You", "ngo": "The NGO", "lister": "The employer"}[e["actor_role"]],
                          "to": e["to_status"], "words": WORDS.get(e["to_status"], ""),
                          "note": e["note"] if (e["actor_role"] != "lister" or e["to_status"] == "not_a_fit") else None}
                         for e in applications.events(a["id"])]
    return out


def ngo_actions(status: str) -> list[str]:
    if status == "interested":
        return ["shared", "declined"]
    if status in ACTIVE:
        return [s for s in EMPLOYER_STAGES + ("not_a_fit",) if s != status]
    return []


def ngo_view(st: helpers.State, a: dict, role: str = "ngo_admin") -> dict:
    s = st.students.get(a["student_id"])
    r = st.row(a["student_id"], a["opp_id"])
    ats = helpers.ats_for(st, a["student_id"], a["opp_id"])
    nxt = ngo_actions(a["status"])
    if role != "ngo_admin":
        nxt = [x for x in nxt if x != "shared"]           # staff put a student forward; an admin shares
    return {"id": a["id"], "student_id": a["student_id"], "opp_id": a["opp_id"], "title": title_of(st, a["opp_id"]),
            "branch": s.branch if s else "", "town": s.college_town if s else "",
            "college": s.college if s else "", "program": s.program if s else "",
            "candidate_code": candidate_code(a["student_id"], settings.candidate_salt()),
            "name": st.contacts.get(a["student_id"]), "status": a["status"], "student_note": a["student_note"],
            "ngo_note": a["ngo_note"], "employer_note": a["employer_note"], "days_in_stage": a["days_in_stage"],
            "updated_at": a["updated_at"], "next": nxt,
            "recommended_by": a.get("recommended_by"), "recommended_at": a.get("recommended_at"),
            "score": r.final_score if r else None, "fit": fit_label(r.final_score, False) if r else None,
            "ats": ats["score"] if ats else None, "has_resume": resumes.meta(a["student_id"]) is not None,
            "can_recommend": a["status"] == "interested" and not a.get("recommended_by"),
            "interviews": [helpers.interview_view(i, "ngo") for i in interviews.list_for(application_id=a["id"])]}


# ---------------- the shared mover ----------------

SHORT = {"shared": "The NGO shared your profile with the employer for “{t}”.",
         "shortlisted": "You are on the shortlist for “{t}”.", "interview": "You have an interview stage for “{t}”.",
         "offered": "You have an offer for “{t}”.", "hired": "Congratulations. You got “{t}”.",
         "declined": "The NGO decided not to share “{t}” yet. See the note.",
         "not_a_fit": "“{t}” was closed for you. See the note."}


def move(sess: Session, app_id: int, to: str, note: str, role: str) -> dict:
    st = state()
    a = applications.get(app_id)
    if a is None:
        raise HTTPException(404, "Not found.")
    if role == "ngo" and to == "shared" and sess.user.role != "ngo_admin":
        raise HTTPException(403, "Only an NGO admin shares a student with an employer. Put the student forward instead.")
    if role == "student" and a["student_id"] != sess.user.student_id:
        raise HTTPException(404, "Not found.")
    if role == "lister" and (a["opp_id"] not in sess.user.listings or app_id not in applications.shared_ids(a["opp_id"])):
        raise HTTPException(404, "Not found.")
    try:
        new = applications.transition(app_id, to, role, sess.user.id, note, known_names=list(st.contacts.values()))
    except ApplicationError as e:
        raise HTTPException(422, str(e))
    st.refresh_load()
    t = title_of(st, a["opp_id"])
    log("application.status", sess, target=f"{a['student_id']}/{a['opp_id']}", detail=f"{a['status']} to {to}")
    if role != "student" and to in SHORT:
        tell(notifications.student_user_id(a["student_id"]), "application", SHORT[to].format(t=t), "/student/applications")
    if to == "shared":
        tell(notifications.owner_user_ids(a["opp_id"]), "application", f"A student was shared with you for “{t}”.", f"/employer/{a['opp_id']}")
        from .listings import email_owners
        email_owners(a["opp_id"], mailer.candidate_shared(t, a["opp_id"]), "candidate_shared")
    if role == "student":
        tell(notifications.ngo_user_ids(), "application",
             f"A student is interested in “{t}”." if to == "interested" else f"A student stepped back from “{t}”.", "/ngo/applications")
    elif role == "lister":
        tell(notifications.ngo_user_ids(), "application", f"An employer moved a student to {to.replace('_', ' ')} for “{t}”.", "/ngo/applications")
    if to == "hired":
        fill_if_full(st, a["opp_id"], t)
    return new


def fill_if_full(st: helpers.State, oid: str, title: str) -> None:
    row = listings.get(oid)
    if row is None or row["status"] != "active":
        return                                      # sample listings are managed by the NGO by hand
    if applications.hired_count(oid) >= row["openings"]:
        listings.close(oid, None, reason="filled")
        st.sync_listing(oid)
        tell(notifications.owner_user_ids(oid) + notifications.ngo_user_ids(), "review", f"“{title}” is filled and now closed.", f"/employer/{oid}")
        for other in applications.list_apps(opp_id=oid, statuses=ACTIVE):
            tell(notifications.student_user_id(other["student_id"]), "application", f"“{title}” has been filled.", "/student/applications")


# ---------------- student ----------------

@router.get("/api/me/applications")
def my_applications(sess: Session = Depends(student_only)):
    st = state()
    return [student_view(st, a) for a in applications.list_apps(student_id=sess.user.student_id)]


@router.post("/api/me/applications")
def show_interest(body: InterestIn, sess: Session = Depends(student_only)):
    st = state()
    sid = sess.user.student_id or ""
    if body.opp_id not in st.opps:
        raise HTTPException(404, "This listing is not open.")
    if helpers.deadline_passed(st.opps[body.opp_id].apply_by):
        raise HTTPException(422, "The last day to apply for this has passed.")
    r = st.row(sid, body.opp_id)
    if r is None or not r.eligible:
        why = "; ".join(c.note for c in (r.checks.values() if r else []) if c.status == "fail") or "it does not fit"
        raise HTTPException(422, f"This one does not fit right now: {why}.")
    try:
        a = applications.create(sid, body.opp_id, body.note, sess.user.id, known_names=list(st.contacts.values()))
    except ApplicationError as e:
        raise HTTPException(422, str(e))
    st.refresh_load()
    log("application.created", sess, target=f"{sid}/{body.opp_id}")
    tell(notifications.ngo_user_ids(), "application", f"A student is interested in “{title_of(st, body.opp_id)}”.", "/ngo/applications")
    return student_view(st, a)


class WithdrawIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    note: str = Field(default="", max_length=500)


@router.post("/api/me/applications/{app_id}/withdraw")
def withdraw(app_id: int, body: WithdrawIn | None = None, sess: Session = Depends(student_only)):
    new = move(sess, app_id, "withdrawn", body.note if body else "", "student")
    return student_view(state(), new)


@router.get("/api/me/saved")
def my_saved(sess: Session = Depends(student_only)):
    st = state()
    sid = sess.user.student_id or ""
    out = []
    for oid in applications.saved(sid):
        o, r = st.opps.get(oid), st.row(sid, oid)
        if o and r:
            out.append({"opp_id": oid, "title": o.title, "org_name": o.org_name, "type": o.type, "city": o.city,
                        "fit": fit_label(r.final_score, False), "eligible": r.eligible})
    return out


@router.put("/api/me/saved/{opp_id}")
def save_listing(opp_id: str, sess: Session = Depends(student_only)):
    if opp_id not in state().opps:
        raise HTTPException(404, "This listing is not open.")
    applications.save(sess.user.student_id or "", opp_id)
    return {"saved": True}


@router.delete("/api/me/saved/{opp_id}")
def unsave_listing(opp_id: str, sess: Session = Depends(student_only)):
    applications.unsave(sess.user.student_id or "", opp_id)
    return {"saved": False}


# ---------------- NGO ----------------

@router.get("/api/applications")
def ngo_applications(status: str | None = None, opp_id: str | None = None, student_id: str | None = None,
                     sess: Session = Depends(ngo_only)):
    st = state()
    if status and status not in applications.STATUSES:
        raise HTTPException(422, "Unknown status.")
    return [ngo_view(st, a, sess.user.role) for a in applications.list_apps(status=status, opp_id=opp_id, student_id=student_id)]


@router.post("/api/applications/{app_id}/status")
def ngo_move(app_id: int, body: MoveIn, sess: Session = Depends(ngo_only)):
    return ngo_view(state(), move(sess, app_id, body.status, body.note, "ngo"), sess.user.role)


class RecommendIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    note: str = Field(default="", max_length=500)


@router.post("/api/applications/{app_id}/recommend")
def recommend(app_id: int, body: RecommendIn, sess: Session = Depends(ngo_only)):
    """Staff put a student forward. The admins get it in their "waiting for your approval" list."""
    st = state()
    try:
        a = applications.recommend(app_id, sess.user.username, body.note, known_names=list(st.contacts.values()))
    except ApplicationError as e:
        raise HTTPException(422, str(e))
    log("application.recommended", sess, target=f"{a['student_id']}/{a['opp_id']}")
    tell(notifications.admin_user_ids(), "application", f"A student was put forward for “{title_of(st, a['opp_id'])}”. Check and share.",
         "/ngo/applications?tab=approve")
    return ngo_view(st, a, sess.user.role)


@router.get("/api/applications/{app_id}/review")
def review_before_sharing(app_id: int, sess: Session = Depends(ngo_only)):
    """Everything an admin needs side by side before sharing: the listing, the match, and the resume read against it."""
    st = state()
    a = applications.get(app_id)
    if a is None or a["student_id"] not in st.students:
        raise HTTPException(404, "Not found.")
    o = st.opps.get(a["opp_id"])
    row = listings.get(a["opp_id"])
    r = st.row(a["student_id"], a["opp_id"])
    log("application.reviewed", sess, target=f"{a['student_id']}/{a['opp_id']}")
    listing = ({**o.model_dump(), "skills": st.norm["opportunities"][o.opp_id]["skills"], "nice": st.norm["opportunities"][o.opp_id].get("nice", [])}
               if o else ({**row["data"], "opp_id": a["opp_id"], "skills": []} if row else {"opp_id": a["opp_id"], "title": a["opp_id"]}))
    return {"application": ngo_view(st, a, sess.user.role), "listing": listing,
            "student": helpers.student_profile(st, a["student_id"]),
            "match": {**helpers.breakdown(r), "overlap": r.overlap, "missing": r.missing, "eligible": r.eligible,
                      "checks": {k: c.model_dump() for k, c in r.checks.items()}} if r else None,
            "ats": helpers.ats_for(st, a["student_id"], a["opp_id"]),
            "events": applications.events(app_id)}


# ---------------- employer ----------------

@router.post("/api/me/applications/{app_id}/status")
def employer_move(app_id: int, body: MoveIn, sess: Session = Depends(employer_only)):
    new = move(sess, app_id, body.status, body.note, "lister")
    return {"id": new["id"], "status": new["status"], "employer_note": new["employer_note"], "days_in_stage": new["days_in_stage"],
            "next": list(NEXT.get(new["status"], ())) + (["not_a_fit"] if new["status"] in NEXT else [])}


def next_start(o) -> str | None:
    """The next batch on or after today, for a training with dates. None when it has no date or its one batch has passed."""
    from datetime import date

    from matcher.learning_plan import next_batch
    if not o.starts_on:
        return None
    d = next_batch(o, date.today())
    return d.isoformat() if d else None


@router.get("/api/me/browse")
def browse(sess: Session = Depends(student_only)):
    """Every live listing as this student sees it: how well it fits, whether they can take it, and why not."""
    st = state()
    sid = sess.user.student_id or ""
    apps = {a["opp_id"]: a for a in applications.list_apps(student_id=sid)}
    saved = set(applications.saved(sid))
    out = [browse_item(r, st.opps[r.opp_id], apps.get(r.opp_id), r.opp_id in saved)
           for r in st.rows_by_student.get(sid, []) if r.opp_id in st.opps]
    out.sort(key=lambda x: (not x["eligible"], -x["score"], x["title"]))
    return out


def browse_item(r, o, a: dict | None, saved: bool) -> dict:
    """One listing as a student sees it. Browse and the listing page share this, so they always agree."""
    return {
        "opp_id": r.opp_id, "title": o.title, "org_name": o.org_name, "type": o.type, "city": o.city, "mode": o.mode,
        "score": r.final_score, "fit": fit_label(r.final_score, False), "eligible": r.eligible,
        "blockers": [c.note for c in r.checks.values() if c.status == "fail"],
        "checks": [c.note for c in r.checks.values() if c.status == "unknown"],
        "pay_min": o.pay_min, "pay_max": o.pay_max, "upfront_cost": o.upfront_cost, "hours_per_week": o.hours_per_week,
        "night_shift": o.night_shift, "overlap": r.overlap, "missing": r.missing, "crowded": r.crowded,
        "description": o.description, "application": {"id": a["id"], "status": a["status"]} if a else None,
        "saved": saved, "apply_by": o.apply_by, "closing_soon": helpers.closing_soon(o.apply_by),
        "starts_on": next_start(o), "duration_weeks": o.duration_weeks}


@router.get("/api/me/browse/{oid}")
def browse_one(oid: str, sess: Session = Depends(student_only)):
    """One live listing in full, as this student sees it. Drafts, listings in review, closed ones and ones past their
    last day to apply are not found, just as Browse and interest leave them out. Nothing about other students is shown
    beyond the crowded flag."""
    st = state()
    sid = sess.user.student_id or ""
    o, r = st.opps.get(oid), st.row(sid, oid)
    if o is None or r is None or helpers.deadline_passed(o.apply_by):
        raise HTTPException(404, "This listing is not open.")
    a = next((x for x in applications.list_apps(student_id=sid) if x["opp_id"] == oid), None)
    d = browse_item(r, o, a, oid in set(applications.saved(sid)))
    if a:
        d["application"]["words"] = WORDS.get(a["status"], "")
    rows = st.rows_by_student[sid]
    d.update(
        job_family=o.job_family, openings=o.openings, languages_required=o.languages_required,
        skills=st.norm["opportunities"].get(oid, {}).get("skills", []),
        nice=st.norm["opportunities"].get(oid, {}).get("nice", []),
        related=[x for x in r.related if x["credit"] >= 0.5], teaches=r.teaches,
        gap_closers=close_the_gap(rows, st.norm, r.missing, exclude=oid) if o.type == "job" else [])
    return d
