"""FastAPI backend. Every route except health, ready and login needs a signed-in account with the right role.

Run: uvicorn api.server:app --port 8000
"""
from __future__ import annotations

import csv
import hashlib
import io
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from matcher import accounts, audit, auth, chat, db, notifications, resume_pdf, settings, store
from matcher.schema import Decision

from . import helpers
from .deps import log, state, student_or_404, tell, who
from .routers import (account, applications as applications_router, casework as casework_router, contact as contact_router, integrations as integrations_router,
                      interviews as interviews_router, leads as leads_router, listings as listings_router, messaging, profile,
                      resumes as resumes_router)
from .security import (COOKIE, NGO, Session, admin_only, client_ip, employer_only, get_session, ngo_only,
                       request_middleware, student_only)


@asynccontextmanager
async def lifespan(_: FastAPI):
    problems = settings.check_production_ready()
    if problems:
        raise RuntimeError(" ".join(problems))
    store.connect().close()
    accounts.bootstrap_admin_if_empty()
    yield


app = FastAPI(title="Opportunity Matcher API", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
app.middleware("http")(request_middleware)


# ---------------------------------------------------------------- public

@app.get("/api/health")
def health():
    return {"ok": True}


@app.get("/api/ready")
def ready():
    problems = []
    try:
        store.connect().close()
    except Exception:
        problems.append("database")
    for k in helpers.REQUIRED:
        if not Path(helpers.PATHS[k]).exists():
            problems.append(k)
    if problems:
        return JSONResponse({"ready": False, "missing": problems}, status_code=503)
    return {"ready": True}


# ---------------------------------------------------------------- sign in

class LoginIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: str = Field(max_length=64)
    password: str = Field(max_length=256)


class PasswordIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    current: str = Field(max_length=256)
    new: str = Field(max_length=256)


def set_cookie(response: Response, token: str) -> None:
    response.set_cookie(COOKIE, token, max_age=settings.session_hours() * 3600, httponly=True, samesite="lax",
                        secure=settings.cookie_secure(), path="/")


@app.post("/api/auth/login")
def login(body: LoginIn, request: Request, response: Response):
    ip = client_ip(request)
    if not auth.ip_allowed(ip):
        audit.record("login.throttled", ip=ip, detail="too many attempts from this address")
        raise HTTPException(429, "Too many sign-in attempts. Wait a few minutes and try again.")
    try:
        user = accounts.authenticate(body.username, body.password, ip)
    except auth.AuthError as e:
        auth.ip_note_attempt(ip)  # only failures count, so a busy office behind one address is not locked out
        raise HTTPException(401, e.public)
    conn = store.connect()
    try:
        token, csrf = auth.create_session(conn, user.id, ip)
    finally:
        conn.close()
    set_cookie(response, token)
    return {"user": user.public(), "csrf": csrf}


@app.get("/api/auth/mode")
def auth_mode():
    return {"demo": settings.demo_login() and not settings.cookie_secure()}


def demo_only() -> None:
    if not (settings.demo_login() and not settings.cookie_secure()):
        raise HTTPException(404, "Not found.")


class DemoLoginIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: str = Field(max_length=64)


@app.get("/api/auth/demo-users")
def demo_users(_: None = Depends(demo_only)):
    return [{"username": u.username, "display_name": u.display_name, "role": u.role,
             "linked": u.student_id or ", ".join(u.listings) or ""} for u in accounts.list_users() if u.is_active]


@app.post("/api/auth/demo-login")
def demo_login(body: DemoLoginIn, request: Request, response: Response, _: None = Depends(demo_only)):
    try:
        user = accounts.demo_sign_in(body.username, client_ip(request))
    except auth.AuthError as e:
        raise HTTPException(404, e.public)
    conn = store.connect()
    try:
        token, csrf = auth.create_session(conn, user.id, client_ip(request))
    finally:
        conn.close()
    set_cookie(response, token)
    return {"user": user.public(), "csrf": csrf}


@app.get("/api/auth/me")
def me(sess: Session = Depends(get_session)):
    return {"user": sess.user.public(), "csrf": sess.csrf}


@app.post("/api/auth/logout")
def logout(response: Response, sess: Session = Depends(get_session)):
    conn = store.connect()
    try:
        auth.delete_session(conn, sess.token)
    finally:
        conn.close()
    log("logout", sess)
    response.delete_cookie(COOKIE, path="/")
    return {"ok": True}


class EmailIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: str | None = Field(default=None, max_length=254)


@app.put("/api/auth/email")
def change_email(body: EmailIn, sess: Session = Depends(get_session)):
    """NGO and employer accounts set the address for emails about listings and interviews. Students use the NGO's contact list."""
    if sess.user.role == "student":
        raise HTTPException(403, "Ask the NGO to update your contact details.")
    try:
        accounts.set_email(sess.user.id, body.email)
    except auth.AuthError as e:
        raise HTTPException(422, e.public)
    log("email.changed", sess)
    return {"user": accounts.get_user(sess.user.id).public()}  # type: ignore[union-attr]


@app.post("/api/auth/change-password")
def change_password(body: PasswordIn, sess: Session = Depends(get_session)):
    try:
        accounts.change_password(sess.user.id, body.current, body.new, keep_token=sess.token)
    except auth.AuthError as e:
        log("password.change_failed", sess, detail=e.reason[:80])
        raise HTTPException(422, e.public)
    log("password.changed", sess)
    return {"ok": True}


# ---------------------------------------------------------------- NGO: students

class WhatIf(BaseModel):
    can_relocate: str | None = None  # yes | no | unknown
    budget: int | None = Field(default=None, ge=0, le=10_000_000)
    family_limits: list[str] | None = Field(default=None, max_length=10)


@app.get("/api/students")
def students(_: Session = Depends(ngo_only)):
    return helpers.student_list(state())


@app.get("/api/config")
def scoring_config(_: Session = Depends(ngo_only)):
    return helpers.scoring_config()


@app.get("/api/students/{sid}")
def student(sid: str, sess: Session = Depends(ngo_only)):
    st = student_or_404(sid)
    log("student.view", sess, target=sid)
    return helpers.student_profile(st, sid)


@app.get("/api/students/{sid}/raw")
def student_raw(sid: str, _: Session = Depends(ngo_only)):
    student_or_404(sid)
    raw = helpers.raw_text(sid)
    if raw is None:
        raise HTTPException(503, "Run make all first")
    return raw


@app.get("/api/students/{sid}/matches")
def matches(sid: str, _: Session = Depends(ngo_only)):
    st = student_or_404(sid)
    return {"what_if": False, "matches": helpers.default_matches(st, sid), "why_not": helpers.why_not(st, sid)}


@app.post("/api/students/{sid}/whatif")
def whatif(sid: str, body: WhatIf, _: Session = Depends(ngo_only)):
    st = student_or_404(sid)
    ov = body.model_dump(exclude_unset=False)
    try:
        return {"what_if": True, "matches": helpers.whatif_matches(st, sid, ov),
                "why_not": helpers.why_not(st, sid, ov)}
    except ValidationError as e:
        raise HTTPException(422, str(e))


@app.get("/api/contacts")
def all_contacts(_: Session = Depends(ngo_only)):
    return state().contacts


@app.get("/api/contacts/{sid}")
def contact(sid: str, _: Session = Depends(ngo_only)):
    return {"name": student_or_404(sid).contacts.get(sid)}


@app.post("/api/intake/pdf")
async def intake_pdf(
    sess: Session = Depends(ngo_only),
    file: UploadFile = File(...),
    branch: str = Form("CSE", max_length=40),
    college_town: str = Form("Khammam", max_length=40),
    grad_year: int = Form(2026, ge=2020, le=2035),
    cgpa: float | None = Form(None, ge=0, le=10),
    can_relocate: str = Form("unknown", max_length=10),
    budget: int | None = Form(None, ge=0, le=10_000_000),
    languages: str = Form("Telugu,English", max_length=60),
    family_limits: str = Form("", max_length=120),
):
    """Read a resume PDF and match the student live. Only PDFs are accepted, and nothing is saved."""
    st = state()
    data = await file.read(resume_pdf.MAX_BYTES + 1)
    try:
        text, pages = resume_pdf.pdf_to_text(data)
    except resume_pdf.ResumeError as e:
        raise HTTPException(422, str(e))
    log("intake.pdf", sess, detail=f"sha256:{hashlib.sha256(data).hexdigest()[:12]} bytes:{len(data)}")
    body = {"branch": branch, "college_town": college_town, "grad_year": grad_year, "cgpa": cgpa,
            "can_relocate": can_relocate, "budget": budget,
            "languages": [x for x in languages.split(",") if x],
            "family_limits": [x for x in family_limits.split(",") if x]}
    try:
        result = helpers.intake_match(st, body, text)
    except ValidationError as e:
        raise HTTPException(422, "; ".join(err["msg"] for err in e.errors()))
    return {**result, "pages": pages}


# ---------------------------------------------------------------- NGO: listings and decisions

@app.get("/api/opportunities")
def opportunities(_: Session = Depends(ngo_only)):
    return helpers.opportunity_list(state())


@app.get("/api/opportunities/{oid}")
def opportunity(oid: str, _: Session = Depends(ngo_only)):
    st = state()
    if oid not in st.opps:
        raise HTTPException(404, "Not found.")
    return helpers.opportunity_detail(st, oid)


class DecisionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    student_id: str = Field(max_length=20)
    opp_id: str = Field(max_length=20)
    rank: int | None = Field(default=None, ge=1, le=50)
    final_score: float | None = None
    decision: str = Field(max_length=10)
    reject_reason: str | None = Field(default=None, max_length=40)
    note: str | None = Field(default=None, max_length=1000)
    what_if: bool = False
    seconds_to_decide: float | None = Field(default=None, ge=0, le=86400)


@app.post("/api/decisions")
def add_decision(body: DecisionIn, sess: Session = Depends(ngo_only)):
    st = state()
    if body.student_id not in st.students or body.opp_id not in st.opps:
        raise HTTPException(404, "Not found.")
    try:
        d = Decision(**body.model_dump())
    except ValidationError as e:
        raise HTTPException(422, "; ".join(err["msg"].replace("Value error, ", "") for err in e.errors()))
    new_id = db.save_decision(d, known_names=list(st.contacts.values()), decided_by=sess.user.username)
    st.refresh_prior()                                     # the staff prior and the learned score use this straight away
    log("decision.saved", sess, target=f"{body.student_id}/{body.opp_id}", detail=body.decision)
    return {"id": new_id}


@app.get("/api/decisions")
def decisions(decision: str | None = None, _: Session = Depends(ngo_only)):
    return [d.model_dump() for d in db.list_decisions(decision)]


@app.get("/api/decisions.csv")
def decisions_csv(_: Session = Depends(ngo_only)):
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(db.COLUMNS)
    for d in db.list_decisions():
        w.writerow([getattr(d, c) if c != "what_if" else int(d.what_if) for c in db.COLUMNS])
    return Response(buf.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": "attachment; filename=decisions.csv"})


# ---------------------------------------------------------------- student: own data only

@app.get("/api/me/student")
def my_student(sess: Session = Depends(student_only)):
    from matcher import applications
    sid = sess.user.student_id or ""
    st = student_or_404(sid)
    apps = {a["opp_id"]: a for a in applications.list_apps(student_id=sid)}
    return helpers.student_self(st, sid, apps, set(applications.saved(sid)))


# ---------------------------------------------------------------- messages

ROLE_TO_SENDER = {"ngo_admin": "ngo", "ngo_staff": "ngo", "student": "student", "employer": "lister"}


class MessageIn(BaseModel):
    body: str = Field(max_length=chat.MAX_LEN + 50)
    about_opp_id: str | None = Field(default=None, max_length=20)


def thread_access(sess: Session, thread_type: str, thread_id: str) -> None:
    """NGO staff may open any thread. A student only their own. An employer only threads for their listings."""
    u = sess.user
    if thread_type not in ("student", "listing"):
        raise HTTPException(404, "Not found.")
    allowed = (u.role in NGO
               or (u.role == "student" and thread_type == "student" and thread_id == u.student_id)
               or (u.role == "employer" and thread_type == "listing" and thread_id in u.listings))
    if not allowed:
        raise HTTPException(404, "Not found.")
    from matcher import listings as listing_store
    st = state()
    known_listing = thread_id in st.opps or listing_store.get(thread_id) is not None   # employers may write about a listing that is not live yet
    if (thread_type == "student" and thread_id not in st.students) or (thread_type == "listing" and not known_listing):
        raise HTTPException(404, "Not found.")


@app.get("/api/threads")
def threads(_: Session = Depends(ngo_only)):
    return chat.list_threads()


@app.get("/api/threads/unread")
def threads_unread(_: Session = Depends(ngo_only)):
    return {"unread": chat.unread_total()}


@app.get("/api/threads/{thread_type}/{thread_id}/messages")
def thread_messages(thread_type: str, thread_id: str, sess: Session = Depends(get_session)):
    thread_access(sess, thread_type, thread_id)
    chat.mark_read(thread_type, thread_id, ROLE_TO_SENDER[sess.user.role])  # type: ignore[arg-type]
    return [m.model_dump() for m in chat.list_messages(thread_type, thread_id)]


@app.post("/api/threads/{thread_type}/{thread_id}/messages")
def post_thread_message(thread_type: str, thread_id: str, body: MessageIn, sess: Session = Depends(get_session)):
    thread_access(sess, thread_type, thread_id)
    st = state()
    if body.about_opp_id and body.about_opp_id not in st.opps:
        raise HTTPException(404, "Not found.")
    try:
        m = chat.Message(thread_type=thread_type, thread_id=thread_id, sender_role=ROLE_TO_SENDER[sess.user.role],  # type: ignore[arg-type]
                         body=body.body, about_opp_id=body.about_opp_id)
    except ValidationError as e:
        raise HTTPException(422, "; ".join(err["msg"].replace("Value error, ", "") for err in e.errors()))
    saved = chat.post_message(m, known_names=list(st.contacts.values()), sender_user_id=sess.user.id)
    log("message.sent", sess, target=f"{thread_type}:{thread_id}")
    if saved.sender_role == "ngo":      # without this, a student or employer only sees the reply if they happen to open Messages
        if thread_type == "student":
            tell(notifications.student_user_id(thread_id), "message", "You have a new message from the NGO.", "/student/messages")
        else:
            tell(notifications.owner_user_ids(thread_id), "message", "You have a new message from the NGO about your listing.",
                 f"/employer/messages?listing={thread_id}")
        alert_outside_app(st, thread_type, thread_id)
    return saved.model_dump()


def alert_outside_app(st, thread_type: str, thread_id: str) -> None:
    """WhatsApp and email for an NGO message, once until it is read: only the first unread NGO message in a thread sends
    anything, so five quick messages make one alert. The alert never carries the message itself, only a link."""
    if chat.unread_from_ngo(thread_type, thread_id) != 1:
        return
    from matcher import contacts, mailer, whatsapp
    from .routers.listings import email_owners
    base = settings.app_url()
    if thread_type == "student":
        link = f"{base}/student/messages"
        whatsapp.send_template(thread_id, "update", ["You have a new message from the NGO.", link],
                               f"Update from the NGO: You have a new message from the NGO. Open: {link}")
        addr = contacts.email(thread_id)
        if addr:
            mailer.send(addr, *mailer.new_message(link), kind="message", recipient=f"student:{thread_id}")
    else:
        o = st.opps.get(thread_id)
        email_owners(thread_id, mailer.new_message(f"{base}/employer/messages?listing={thread_id}", o.title if o else None), "message")


# ---------------------------------------------------------------- admin: accounts and audit log

class UserIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: str = Field(max_length=40)
    display_name: str = Field(max_length=80)
    role: str = Field(max_length=20)
    student_id: str | None = Field(default=None, max_length=20)
    listings: list[str] = Field(default_factory=list, max_length=50)
    email: str | None = Field(default=None, max_length=254)


class UserPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    is_active: bool | None = None
    display_name: str | None = Field(default=None, max_length=80)
    listings: list[str] | None = Field(default=None, max_length=50)
    email: str | None = Field(default=None, max_length=254)


def public_user(u: accounts.User) -> dict:
    d = u.public()
    d["locked"] = bool(u.locked_until and u.locked_until > auth.iso(auth.now()))
    return d


@app.get("/api/admin/users")
def admin_users(_: Session = Depends(admin_only)):
    return [public_user(u) for u in accounts.list_users()]


@app.post("/api/admin/users")
def admin_create_user(body: UserIn, sess: Session = Depends(admin_only)):
    st = state()
    if body.role == "student" and body.student_id not in st.students:
        raise HTTPException(422, "There is no student with that ID.")
    bad = [o for o in body.listings if o not in st.opps]
    if bad:
        raise HTTPException(422, f"There is no listing {bad[0]}.")
    try:
        u, temp = accounts.create_user(body.username, body.display_name, body.role, student_id=body.student_id,
                                       listings=body.listings, email=None if body.role == "student" else body.email)
    except auth.AuthError as e:
        raise HTTPException(422, e.public)
    log("user.created", sess, target=u.username, detail=u.role)
    return {"user": public_user(u), "temporary_password": temp}


@app.patch("/api/admin/users/{user_id}")
def admin_patch_user(user_id: int, body: UserPatch, sess: Session = Depends(admin_only)):
    target = accounts.get_user(user_id)
    if target is None:
        raise HTTPException(404, "Not found.")
    try:
        if body.is_active is not None and body.is_active != target.is_active:
            if user_id == sess.user.id and not body.is_active:
                raise auth.AuthError("You cannot deactivate your own account.")
            accounts.set_active(user_id, body.is_active)
            log("user.reactivated" if body.is_active else "user.deactivated", sess, target=target.username)
        if body.display_name is not None:
            accounts.set_display_name(user_id, body.display_name)
            log("user.renamed", sess, target=target.username)
        if body.listings is not None:
            bad = [o for o in body.listings if o not in state().opps]
            if bad:
                raise auth.AuthError(f"There is no listing {bad[0]}.")
            accounts.set_listings(user_id, body.listings)
            log("user.listings_changed", sess, target=target.username, detail=",".join(body.listings))
        if "email" in body.model_fields_set:
            accounts.set_email(user_id, body.email)
            log("user.email_changed", sess, target=target.username)
    except auth.AuthError as e:
        raise HTTPException(422, e.public)
    return public_user(accounts.get_user(user_id))  # type: ignore[arg-type]


@app.post("/api/admin/users/{user_id}/reset-password")
def admin_reset_password(user_id: int, sess: Session = Depends(admin_only)):
    target = accounts.get_user(user_id)
    if target is None:
        raise HTTPException(404, "Not found.")
    temp = accounts.reset_password(user_id)
    log("user.password_reset", sess, target=target.username)
    return {"temporary_password": temp}


@app.get("/api/admin/audit")
def admin_audit(action: str | None = None, username: str | None = None, since: str | None = None,
                until: str | None = None, limit: int = 200, _: Session = Depends(admin_only)):
    return audit.list_events(action=action, username=username, since=since, until=until, limit=limit)


@app.get("/api/admin/audit.csv")
def admin_audit_csv(action: str | None = None, username: str | None = None, since: str | None = None,
                    until: str | None = None, sess: Session = Depends(admin_only)):
    log("audit.exported", sess)
    ev = audit.list_events(action=action, username=username, since=since, until=until, limit=5000)
    return Response(audit.to_csv(ev), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=audit.csv"})


for r in (listings_router.router, applications_router.router, profile.router, casework_router.router, account.router,
          resumes_router.router, messaging.router, leads_router.router, interviews_router.router, integrations_router.router,
          contact_router.router):
    app.include_router(r)


# ---------------------------------------------------------------- web app (served last so it never hides an API route)

_dist = Path(__file__).resolve().parents[1] / "web" / "dist"
if _dist.exists():
    from fastapi.staticfiles import StaticFiles
    from starlette.exceptions import HTTPException as StarletteHTTPException

    class SPAFiles(StaticFiles):
        async def get_response(self, path: str, scope):
            try:
                return await super().get_response(path, scope)
            except StarletteHTTPException as e:
                if e.status_code == 404 and not path.startswith("api/"):
                    return await super().get_response("index.html", scope)
                raise

    app.mount("/", SPAFiles(directory=_dist, html=True), name="web")
