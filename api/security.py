"""Sign-in checks, roles, CSRF, security headers, request logging and error handling."""
from __future__ import annotations

import json
import logging
import re
import time
import uuid
from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request
from fastapi.responses import JSONResponse

from matcher import accounts, auth, settings, store

COOKIE = "session"
UNSAFE = {"POST", "PUT", "PATCH", "DELETE"}
NGO = ("ngo_admin", "ngo_staff")
OPEN_WHEN_PASSWORD_MUST_CHANGE = {"/api/auth/me", "/api/auth/logout", "/api/auth/change-password"}
MAX_JSON_BYTES = 64 * 1024
MAX_PDF_BYTES = 6 * 1024 * 1024
MAX_BULK_BYTES = 60 * 1024 * 1024
LIMITS = [  # (path pattern, largest request body)
    (re.compile(r"^/api/(intake/pdf|me/resume|students/[^/]+/resume)$"), MAX_PDF_BYTES),
    (re.compile(r"^/api/resumes/bulk$"), MAX_BULK_BYTES),
    (re.compile(r"^/api/(whatsapp|fireflies)/webhook$"), 1024 * 1024),
    (re.compile(r"^/api/interviews/\d+/notes$"), 256 * 1024),
]
FRAMEABLE = re.compile(r"^/api/(students/[^/]+|me)/resume\.pdf$")   # the resume viewer shows these inside the app


def body_limit(path: str) -> int:
    return next((n for pat, n in LIMITS if pat.match(path)), MAX_JSON_BYTES)

access_log = logging.getLogger("matcher.access")


@dataclass
class Session:
    user: accounts.User
    token: str
    csrf: str
    ip: str


def client_ip(request: Request) -> str:
    import os
    if os.environ.get("TRUST_PROXY", "0") == "1":
        fwd = request.headers.get("x-forwarded-for", "")
        if fwd:
            return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def get_session(request: Request) -> Session:
    token = request.cookies.get(COOKIE)
    conn = store.connect()
    try:
        row = auth.load_session(conn, token)
        if row is None:
            raise HTTPException(401, "Please sign in.")
        user = accounts.get_user(row["user_id"])
        if user is None or not user.is_active:
            auth.delete_session(conn, token)
            raise HTTPException(401, "Please sign in.")
    finally:
        conn.close()
    if request.method in UNSAFE and not auth.csrf_ok(row["csrf_token"], request.headers.get("x-csrf-token")):
        raise HTTPException(403, "The page is out of date. Reload it and try again.")
    if user.must_change_password and request.url.path not in OPEN_WHEN_PASSWORD_MUST_CHANGE:
        raise HTTPException(403, "Change your password first.")
    request.state.username = user.username
    return Session(user=user, token=token or "", csrf=row["csrf_token"], ip=client_ip(request))


def require(*roles: str):
    """Dependency: the signed-in account must have one of these roles."""
    def dep(sess: Session = Depends(get_session)) -> Session:
        if sess.user.role not in roles:
            raise HTTPException(403, "You do not have access to this.")
        return sess
    return dep


ngo_only = require(*NGO)
admin_only = require("ngo_admin")
student_only = require("student")
employer_only = require("employer")


# ---------- middleware ----------

def security_headers(path: str = "") -> dict[str, str]:
    h = {
        "Content-Security-Policy": ("default-src 'self'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
                                    "font-src https://fonts.gstatic.com; img-src 'self' data:; frame-ancestors 'none'; "
                                    "base-uri 'self'; form-action 'self'"),
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "Referrer-Policy": "same-origin",
        "Permissions-Policy": "camera=(), microphone=(), geolocation=(), payment=(), usb=()",
    }
    if FRAMEABLE.match(path):                       # a PDF the app itself shows in a frame, and nothing else may
        h["Content-Security-Policy"] = "frame-ancestors 'self'"
        h["X-Frame-Options"] = "SAMEORIGIN"
    if settings.cookie_secure():
        h["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return h


async def request_middleware(request: Request, call_next):
    rid = uuid.uuid4().hex[:12]
    request.state.request_id = rid
    request.state.username = None
    started = time.perf_counter()
    limit = body_limit(request.url.path)
    try:
        length = int(request.headers.get("content-length") or 0)
    except ValueError:
        length = 0
    if length > limit:
        response = JSONResponse({"detail": "That request is too large.", "request_id": rid}, status_code=413)
    else:
        try:
            response = await call_next(request)
        except Exception:
            access_log.exception("unhandled error request_id=%s path=%s", rid, request.url.path)
            response = JSONResponse({"detail": "Something went wrong.", "request_id": rid}, status_code=500)
    for k, v in security_headers(request.url.path).items():
        response.headers[k] = v
    response.headers["X-Request-ID"] = rid
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    access_log.info(json.dumps({
        "t": time.strftime("%Y-%m-%dT%H:%M:%S"), "method": request.method, "path": request.url.path,
        "status": response.status_code, "ms": round((time.perf_counter() - started) * 1000, 1),
        "request_id": rid, "user": getattr(request.state, "username", None)}))
    return response
