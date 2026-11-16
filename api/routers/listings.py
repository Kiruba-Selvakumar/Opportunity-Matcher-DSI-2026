"""Employer listings: post, edit, submit, close, reopen, copy. NGO review queue."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from matcher import broadcast, accounts, applications, interviews, leads, listings, mailer, notifications
from matcher.applications import EMPLOYER_STAGES, NEXT
from matcher.listings import ListingError, ListingIn
from matcher.skills import normalize_opportunity

from .. import helpers
from ..deps import log, state, tell
from ..security import Session, admin_only, employer_only, ngo_only

router = APIRouter()
EMPLOYER_SEES = EMPLOYER_STAGES + ("not_a_fit",)


def _422(e: ValidationError) -> HTTPException:
    return HTTPException(422, "; ".join(f"{'.'.join(str(x) for x in err['loc'])}: {err['msg'].replace('Value error, ', '')}" for err in e.errors()))


def owned_row(sess: Session, oid: str) -> dict:
    """An employer listing the signed-in employer owns. Anything else is "not found"."""
    row = listings.get(oid)
    if row is None or row["owner_user_id"] != sess.user.id:
        raise HTTPException(404, "Not found.")
    return row


def form_of(row: dict) -> dict:
    return row["data"]


def view(row: dict) -> dict:
    return {"opp_id": row["opp_id"], "status": row["status"], "editable": True, "managed": True,
            "review_note": row["review_note"], "reviewed_at": row["reviewed_at"], "closed_reason": row["closed_reason"],
            "was_approved": bool(row["was_approved"]), "edited_since_review": bool(row["edited_since_review"]),
            "form": form_of(row), "created_at": row["created_at"], "updated_at": row["updated_at"]}


def applicants_for(st: helpers.State, oid: str) -> list[dict]:
    """Students the NGO has shared with this listing, as an employer may see them: a code, never a name."""
    from matcher.privacy import candidate_code
    from matcher import settings
    seen = applications.shared_ids(oid)
    out = []
    for a in applications.list_apps(opp_id=oid):
        if a["id"] not in seen or a["status"] not in EMPLOYER_SEES:
            continue
        s = st.students.get(a["student_id"])
        if s is None:
            continue
        r = st.row(a["student_id"], oid)
        out.append({"id": a["id"], "candidate_code": candidate_code(s.student_id, settings.candidate_salt()),
                    "branch": s.branch, "town": s.college_town, "cgpa": s.cgpa, "status": a["status"],
                    "overlap": r.overlap if r else [], "missing": r.missing if r else [],
                    "student_note": a["student_note"], "employer_note": a["employer_note"],
                    "days_in_stage": a["days_in_stage"],
                    "next": list(NEXT.get(a["status"], ())) + (["not_a_fit"] if a["status"] in NEXT else []),
                    "interviews": [helpers.interview_view(i, "employer") for i in interviews.list_for(application_id=a["id"])],
                    "can_schedule": a["status"] in ("shortlisted", "interview")})
    return out


def listing_row_summary(st: helpers.State, oid: str) -> dict | None:
    row = listings.get(oid)
    if row is not None:                                   # posted by an employer
        d = row["data"]
        active = oid in st.opps
        return {"opp_id": oid, "title": d["title"], "org_name": d["org_name"], "type": d["type"], "city": d["city"],
                "mode": d["mode"], "status": row["status"], "managed": True, "editable": True, "openings": row["openings"],
                "eligible_count": sum(r.eligible for r in st.rows_by_opp.get(oid, [])) if active else 0,
                "applicants": len([a for a in applications.list_apps(opp_id=oid) if a["id"] in applications.shared_ids(oid)]),
                "review_note": row["review_note"], "updated_at": row["updated_at"], "apply_by": d.get("apply_by"),
                "closing_soon": helpers.closing_soon(d.get("apply_by")) and row["status"] == "active"}
    o = st.opps.get(oid)
    if o is None:
        return None
    return {"opp_id": oid, "title": o.title, "org_name": o.org_name, "type": o.type, "city": o.city, "mode": o.mode,
            "status": "active", "managed": False, "editable": False, "openings": o.openings,
            "eligible_count": sum(r.eligible for r in st.rows_by_opp.get(oid, [])),
            "applicants": len(applications.shared_ids(oid)), "review_note": None, "updated_at": None,
            "apply_by": o.apply_by, "closing_soon": helpers.closing_soon(o.apply_by)}


@router.get("/api/me/listings")
def my_listings(sess: Session = Depends(employer_only)):
    st = state()
    out = [listing_row_summary(st, o) for o in sess.user.listings]
    return [x for x in out if x]


def detail(st: helpers.State, sess: Session, oid: str) -> dict:
    row = listings.get(oid)
    base: dict
    if oid in st.opps:
        base = helpers.employer_listing(st, oid)
    elif row is not None:
        opp = listings.to_opportunity(row)
        n = normalize_opportunity(opp, st.enc)
        base = {"opp_id": oid, "type": opp.type, "title": opp.title, "org_name": opp.org_name, "job_family": opp.job_family,
                "city": opp.city, "mode": opp.mode, "pay_min": opp.pay_min, "pay_max": opp.pay_max, "upfront_cost": opp.upfront_cost,
                "hours_per_week": opp.hours_per_week, "night_shift": opp.night_shift, "safety_score": opp.safety_score,
                "languages_required": opp.languages_required, "skills": n["skills"], "eligible_count": 0,
                "total_students": len(st.students), "candidates": []}
    else:
        raise HTTPException(404, "Not found.")
    base.update(listing_row_summary(st, oid) or {})
    base["description"] = (row["data"].get("description", "") if row else "")
    base["form"] = row["data"] if row else None
    base["review_note"] = row["review_note"] if row else None
    base["closed_reason"] = row["closed_reason"] if row else None
    base["applicants"] = applicants_for(st, oid)
    return base


@router.get("/api/me/listings/{oid}")
def my_listing(oid: str, sess: Session = Depends(employer_only)):
    st = state()
    if oid not in sess.user.listings:
        raise HTTPException(404, "Not found.")
    log("listing.view", sess, target=oid)
    return detail(st, sess, oid)


def no_mentors(body: ListingIn) -> None:
    if body.type == "mentor":
        raise HTTPException(422, "Mentor listings are added by the NGO.")


@router.post("/api/me/listings")
def create_listing(body: ListingIn, submit: bool = False, sess: Session = Depends(employer_only)):
    st = state()
    no_mentors(body)
    try:
        row = listings.create(sess.user.id, body, submit=submit, known_names=list(st.contacts.values()))
    except ListingError as e:
        raise HTTPException(422, str(e))
    log("listing.created", sess, target=row["opp_id"], detail="submitted" if submit else "draft")
    if submit:
        tell(notifications.admin_user_ids(), "review", "A listing is waiting for your review.", "/ngo/opportunities?tab=review")
    return {**view(row), "title": row["data"]["title"]}


@router.put("/api/me/listings/{oid}")
def update_listing(oid: str, body: ListingIn, submit: bool = False, sess: Session = Depends(employer_only)):
    st = state()
    owned_row(sess, oid)
    no_mentors(body)
    try:
        row = listings.update(oid, sess.user.id, body, submit=submit, known_names=list(st.contacts.values()))
    except ListingError as e:
        raise HTTPException(422, str(e))
    st.sync_listing(oid)                                   # an edited active listing leaves matching until it is reviewed again
    log("listing.updated", sess, target=oid, detail=row["status"])
    if row["status"] == "pending":
        tell(notifications.admin_user_ids(), "review", "A listing is waiting for your review.", "/ngo/opportunities?tab=review")
    return view(row)


def _act(sess: Session, oid: str, fn, action: str, notify_ngo: str | None = None) -> dict:
    owned_row(sess, oid)
    st = state()
    try:
        row = fn()
    except ListingError as e:
        raise HTTPException(422, str(e))
    st.sync_listing(oid)
    log(action, sess, target=oid, detail=row["status"])
    if notify_ngo:
        tell(notifications.admin_user_ids(), "review", notify_ngo, "/ngo/opportunities?tab=review")
    return view(row)


@router.post("/api/me/listings/{oid}/submit")
def submit_listing(oid: str, sess: Session = Depends(employer_only)):
    return _act(sess, oid, lambda: listings.submit(oid, sess.user.id), "listing.submitted", "A listing is waiting for your review.")


@router.post("/api/me/listings/{oid}/close")
def close_listing(oid: str, sess: Session = Depends(employer_only)):
    out = _act(sess, oid, lambda: listings.close(oid, sess.user.id), "listing.closed")
    for a in applications.list_apps(opp_id=oid, statuses=applications.ACTIVE):
        tell(notifications.student_user_id(a["student_id"]), "application", "A listing you were interested in has closed.", "/student/applications")
    return out


@router.post("/api/me/listings/{oid}/reopen")
def reopen_listing(oid: str, sess: Session = Depends(employer_only)):
    out = _act(sess, oid, lambda: listings.reopen(oid, sess.user.id), "listing.reopened")
    if out["status"] == "pending":
        tell(notifications.admin_user_ids(), "review", "A listing is waiting for your review.", "/ngo/opportunities?tab=review")
    return out


@router.post("/api/me/listings/{oid}/copy")
def copy_listing(oid: str, sess: Session = Depends(employer_only)):
    owned_row(sess, oid)
    try:
        row = listings.copy(oid, sess.user.id, known_names=list(state().contacts.values()))
    except ListingError as e:
        raise HTTPException(422, str(e))
    log("listing.created", sess, target=row["opp_id"], detail=f"copy of {oid}")
    return view(row)


# ---------------- NGO review queue ----------------

class ReviewIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decision: str = Field(max_length=10)
    safety_score: int = Field(default=3, ge=1, le=5)
    note: str = Field(default="", max_length=500)
    tell_students: bool = False                         # WhatsApp the students it fits best as soon as it goes live


AUTO_TELL_LIMIT = 50


def tell_best_fits(st: helpers.State, oid: str, sess: Session) -> int:
    """A listing just went live. The app picks the students it fits best, and messages those who agreed to WhatsApp."""
    opp = st.opps.get(oid)
    if opp is None:
        return 0
    planned = broadcast.plan("opportunity", st.students, rows_for_opp=st.rows_by_opp.get(oid), opp=opp, limit=AUTO_TELL_LIMIT,
                             known_names=list(st.contacts.values()))
    if not planned["reachable"]:
        return 0
    res = broadcast.send(planned)
    log("broadcast.sent", sess, target=oid, detail=f"{res['queued']} queued when it went live, batch {res['batch_id']}")
    return res["queued"]


def review_item(st: helpers.State, row: dict) -> dict:
    opp = listings.to_opportunity(row)
    mapped = len(normalize_opportunity(opp, st.enc)["skills"])
    owner = accounts.get_user(row["owner_user_id"])
    return {"opp_id": row["opp_id"], "status": row["status"], "form": row["data"], "safety_score": row["safety_score"],
            "review_note": row["review_note"], "reviewed_by": row["reviewed_by"], "updated_at": row["updated_at"],
            "owner": owner.display_name if owner else "", "was_approved": bool(row["was_approved"]),
            "edited_since_review": bool(row["edited_since_review"]), "flags": listings.review_flags(row, mapped),
            "mapped_skills": mapped}


@router.get("/api/listings/review")
def review_queue(status: str = "pending", _: Session = Depends(ngo_only)):
    st = state()
    if status not in ("all", *listings.STATUSES):
        raise HTTPException(422, "Unknown status.")
    rows = listings.list_all(None if status == "all" else status)
    return [review_item(st, r) for r in rows if r["status"] != "draft"]


def email_owners(oid: str, subject_body: tuple[str, str], kind: str) -> int:
    """Email every active owner of a listing who has an email on their account. Returns how many were queued."""
    owners = notifications.owner_user_ids(oid)
    n = 0
    for uid, addr in zip(owners, [accounts.get_user(u).email for u in owners]):  # type: ignore[union-attr]
        if addr:
            mailer.send(addr, *subject_body, kind=kind, recipient=f"user:{uid}")
            n += 1
    return n


@router.post("/api/listings/{oid}/review")
def review_listing(oid: str, body: ReviewIn, sess: Session = Depends(admin_only)):
    st = state()
    try:
        row = listings.review(oid, sess.user.username, body.decision, body.safety_score, body.note)
    except ListingError as e:
        raise HTTPException(422, str(e))
    st.sync_listing(oid)
    title = row["data"]["title"]
    log("listing.reviewed", sess, target=oid, detail=body.decision)
    ok = row["status"] == "active"
    tell(notifications.owner_user_ids(oid), "review",
         f"Your listing “{title}” was approved and is live." if ok else f"Your listing “{title}” was not approved. See the note.",
         f"/employer/{oid}")
    emailed = email_owners(oid, mailer.listing_reviewed(title, ok, row["review_note"], oid), "listing_reviewed")
    told = tell_best_fits(st, oid, sess) if ok and body.tell_students else 0
    return {**review_item(st, row), "emailed": emailed, "told": told}


# ---------------- NGO admins post and edit listings themselves ----------------

class NgoListingIn(ListingIn):
    owner_username: str | None = Field(default=None, max_length=40)    # an employer account that should manage it too
    safety_score: int = Field(default=4, ge=1, le=5)
    lead_id: int | None = None                                          # the WhatsApp lead this came from
    tell_students: bool = False                                         # WhatsApp the students it fits best when it goes live


def _listing_part(body: NgoListingIn) -> ListingIn:
    return ListingIn(**body.model_dump(exclude={"owner_username", "safety_score", "lead_id", "tell_students"}))


@router.post("/api/listings")
def ngo_create_listing(body: NgoListingIn, sess: Session = Depends(admin_only)):
    """An admin posts a listing: it is reviewed by the admin who posts it, so it goes live at once."""
    st = state()
    owner = accounts.get_by_username(body.owner_username) if body.owner_username else None
    if body.owner_username and (owner is None or owner.role != "employer" or not owner.is_active):
        raise HTTPException(422, "There is no active employer account with that username.")
    try:
        row = listings.create(owner.id if owner else sess.user.id, _listing_part(body), submit=True,
                              known_names=list(st.contacts.values()), link_owner=owner is not None)
        row = listings.review(row["opp_id"], sess.user.username, "approve", body.safety_score, "Posted by the NGO.")
    except ListingError as e:
        raise HTTPException(422, str(e))
    st.sync_listing(row["opp_id"])
    if body.lead_id is not None:
        leads.set_status(body.lead_id, "mapped", sess.user.username, mapped_opp_id=row["opp_id"])
    log("listing.created", sess, target=row["opp_id"], detail="by the NGO" + (f" for {owner.username}" if owner else ""))
    if owner:
        tell(owner.id, "review", f"The NGO posted “{row['data']['title']}” for you. It is live.", f"/employer/{row['opp_id']}")
    told = tell_best_fits(st, row["opp_id"], sess) if body.tell_students else 0
    return {**review_item(st, row), "told": told}


@router.get("/api/listings/{oid}/form")
def ngo_listing_form(oid: str, _: Session = Depends(admin_only)):
    row = listings.get(oid)
    if row is None:
        raise HTTPException(404, "Only listings posted in the app can be edited here.")
    return {"opp_id": oid, "status": row["status"], "form": row["data"], "safety_score": row["safety_score"]}


@router.put("/api/listings/{oid}")
def ngo_edit_listing(oid: str, body: NgoListingIn, sess: Session = Depends(admin_only)):
    st = state()
    try:
        row = listings.ngo_edit(oid, _listing_part(body), known_names=list(st.contacts.values()),
                                safety_score=body.safety_score if "safety_score" in body.model_fields_set else None)
    except ListingError as e:
        raise HTTPException(422, str(e))
    st.sync_listing(oid)
    log("listing.updated", sess, target=oid, detail="by the NGO")
    return review_item(st, row)


@router.post("/api/listings/{oid}/close")
def ngo_close_listing(oid: str, sess: Session = Depends(admin_only)):
    row = listings.get(oid)
    if row is None:
        raise HTTPException(404, "Not found.")
    try:
        row = listings.close(oid, None, reason="closed by the NGO")
    except ListingError as e:
        raise HTTPException(422, str(e))
    state().sync_listing(oid)
    log("listing.closed", sess, target=oid, detail="by the NGO")
    tell(notifications.owner_user_ids(oid), "review", f"The NGO closed your listing “{row['data']['title']}”.", f"/employer/{oid}")
    return review_item(state(), row)
