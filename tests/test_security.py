"""Sign-in, sessions, CSRF, lockout, headers, errors, the admin area and the audit log."""
import json

import pytest

from api import helpers, server
from matcher import accounts, auth, settings, store

from .conftest import PASSWORD


def test_login_sets_a_safe_cookie_and_returns_no_secrets(make_client):
    c = make_client()
    r = c.post("/api/auth/login", json={"username": "STAFF1", "password": PASSWORD})  # username is case-insensitive
    assert r.status_code == 200
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=lax" in cookie and "secure" not in cookie
    body = json.dumps(r.json())
    assert "password" not in body.replace("must_change_password", "") and "scrypt" not in body
    assert r.json()["user"]["role"] == "ngo_staff" and r.json()["csrf"]


def test_secure_cookie_in_secure_mode(make_client, monkeypatch):
    monkeypatch.setenv("COOKIE_SECURE", "1")
    r = make_client().post("/api/auth/login", json={"username": "staff1", "password": PASSWORD})
    assert "secure" in r.headers["set-cookie"].lower()
    assert "strict-transport-security" in r.headers


def test_wrong_password_and_unknown_user_look_the_same(make_client):
    c = make_client()
    a = c.post("/api/auth/login", json={"username": "staff1", "password": "wrong wrong wrong"})
    b = c.post("/api/auth/login", json={"username": "nobody", "password": "wrong wrong wrong"})
    assert a.status_code == b.status_code == 401 and a.json() == b.json()


def test_logout_ends_the_session(make_client):
    c = make_client("staff1")
    assert c.get("/api/auth/me").status_code == 200
    assert c.post("/api/auth/logout").status_code == 200
    assert c.get("/api/auth/me").status_code == 401


def test_a_forged_or_expired_session_is_refused(make_client):
    c = make_client()
    c.cookies.set("session", "forged-token")
    assert c.get("/api/auth/me").status_code == 401
    c2 = make_client("staff1")
    conn = store.connect()
    conn.execute("UPDATE sessions SET expires_at = '2000-01-01T00:00:00+00:00'")
    assert c2.get("/api/auth/me").status_code == 401


def test_csrf_token_is_required_for_changes(make_client):
    c = make_client("staff1")
    body = {"student_id": "S004", "opp_id": "J001", "decision": "accept"}
    good = c.headers["X-CSRF-Token"]
    del c.headers["X-CSRF-Token"]
    assert c.post("/api/decisions", json=body).status_code == 403
    c.headers["X-CSRF-Token"] = "wrong"
    assert c.post("/api/decisions", json=body).status_code == 403
    c.headers["X-CSRF-Token"] = good
    assert c.post("/api/decisions", json=body).status_code == 200
    assert c.get("/api/students").status_code == 200  # reads do not need the token


def test_forced_password_change_blocks_everything_else(make_client):
    u, temp = accounts.create_user("newofficer", "New Officer", "ngo_staff")
    c = make_client("newofficer", password=temp)
    assert c.get("/api/auth/me").json()["user"]["must_change_password"] is True
    assert c.get("/api/students").status_code == 403
    assert c.post("/api/auth/change-password", json={"current": temp, "new": "short"}).status_code == 422
    assert c.post("/api/auth/change-password", json={"current": temp, "new": "a much better passphrase"}).status_code == 200
    assert c.get("/api/students").status_code == 200


def test_lockout_through_the_api(make_client):
    accounts.create_user("lockme1", "Lock Me", "ngo_staff", password=PASSWORD, must_change=False)
    c = make_client()
    for _ in range(5):
        assert c.post("/api/auth/login", json={"username": "lockme1", "password": "wrong wrong wrong"}).status_code == 401
    r = c.post("/api/auth/login", json={"username": "lockme1", "password": PASSWORD})
    assert r.status_code == 401 and "locked" in r.json()["detail"]


def test_ip_throttle_through_the_api(make_client):
    c = make_client()
    codes = [c.post("/api/auth/login", json={"username": "nobody", "password": "x" * 12}).status_code for _ in range(22)]
    assert codes[:20] == [401] * 20 and codes[20:] == [429, 429]


def test_unknown_fields_and_oversized_bodies_are_rejected(make_client):
    c = make_client()
    assert c.post("/api/auth/login", json={"username": "a", "password": "b", "extra": 1}).status_code == 422
    big = c.post("/api/auth/login", json={"username": "a", "password": "x" * 70_000})
    assert big.status_code == 413


def test_security_headers_and_no_caching_of_api_responses(make_client):
    r = make_client().get("/api/health")
    assert "default-src 'self'" in r.headers["content-security-policy"]
    assert r.headers["x-content-type-options"] == "nosniff" and r.headers["x-frame-options"] == "DENY"
    assert r.headers["referrer-policy"] == "same-origin" and r.headers["cache-control"] == "no-store"
    assert r.headers["x-request-id"]


def test_server_errors_hide_details_and_return_a_request_id(make_client, monkeypatch):
    c = make_client("staff1", raise_exceptions=False)
    monkeypatch.setattr(helpers, "student_list", lambda st: (_ for _ in ()).throw(RuntimeError("secret internals")))
    r = c.get("/api/students")
    assert r.status_code == 500
    assert r.json()["detail"] == "Something went wrong." and r.json()["request_id"]
    assert "secret internals" not in r.text and "Traceback" not in r.text


def test_access_log_has_no_cookie_or_body(make_client, caplog):
    import logging
    caplog.set_level(logging.INFO, logger="matcher.access")
    make_client("staff1").post("/api/decisions", json={"student_id": "S005", "opp_id": "J001", "decision": "flag",
                                                        "note": "private note text"})
    text = " ".join(r.getMessage() for r in caplog.records)
    assert '"user": "staff1"' in text and "/api/decisions" in text
    assert "private note text" not in text and "session=" not in text.lower()


def test_ready_and_health(make_client):
    c = make_client()
    assert c.get("/api/health").json() == {"ok": True}
    assert c.get("/api/ready").json() == {"ready": True}


def test_secure_mode_needs_a_real_candidate_salt(monkeypatch):
    monkeypatch.setenv("COOKIE_SECURE", "1")
    monkeypatch.delenv("CANDIDATE_SALT", raising=False)
    assert settings.check_production_ready()
    monkeypatch.setenv("CANDIDATE_SALT", "x" * 32)
    assert settings.check_production_ready() == []


# ---------------- admin area and audit log ----------------

def test_admin_creates_a_student_account_end_to_end(make_client):
    admin = make_client("admin1")
    r = admin.post("/api/admin/users", json={"username": "stud3", "display_name": "Divya", "role": "student", "student_id": "S003"})
    assert r.status_code == 200, r.text
    temp = r.json()["temporary_password"]
    assert len(temp) == 16 and r.json()["user"]["must_change_password"]
    assert "temporary_password" not in json.dumps(admin.get("/api/admin/users").json())  # shown once only
    c = make_client("stud3", password=temp)
    assert c.get("/api/me/student").status_code == 403           # blocked until the password is changed
    assert c.post("/api/auth/change-password", json={"current": temp, "new": "my own good passphrase"}).status_code == 200
    assert c.get("/api/me/student").json()["profile"]["student_id"] == "S003"


def test_admin_validation_and_protection(make_client):
    admin = make_client("admin1")
    make = lambda **kw: admin.post("/api/admin/users", json=kw)  # noqa: E731
    assert make(username="x", display_name="X", role="ngo_staff").status_code == 422
    assert make(username="newstud9", display_name="X", role="student", student_id="S999").status_code == 422
    assert make(username="newstud9", display_name="X", role="student", student_id="S001").status_code == 422  # S001 has an account
    assert make(username="newemp9", display_name="X", role="employer", listings=["NOPE"]).status_code == 422
    assert make(username="staff1", display_name="X", role="ngo_staff").status_code == 422                       # taken
    assert make(username="ok9999", display_name="X", role="ngo_staff", is_admin=True).status_code == 422       # unknown field
    me = admin.get("/api/auth/me").json()["user"]["id"]
    assert admin.patch(f"/api/admin/users/{me}", json={"is_active": False}).status_code == 422                 # not yourself


def test_deactivate_reactivate_and_reset(make_client):
    admin = make_client("admin1")
    u, _ = accounts.create_user("tempstaff", "T", "ngo_staff", password=PASSWORD, must_change=False)
    c = make_client("tempstaff")
    assert admin.patch(f"/api/admin/users/{u.id}", json={"is_active": False}).json()["is_active"] is False
    assert c.get("/api/students").status_code == 401                                   # the live session is gone
    assert make_client().post("/api/auth/login", json={"username": "tempstaff", "password": PASSWORD}).status_code == 401
    admin.patch(f"/api/admin/users/{u.id}", json={"is_active": True})
    temp = admin.post(f"/api/admin/users/{u.id}/reset-password").json()["temporary_password"]
    assert make_client().post("/api/auth/login", json={"username": "tempstaff", "password": PASSWORD}).status_code == 401
    assert make_client().post("/api/auth/login", json={"username": "tempstaff", "password": temp}).status_code == 200


def test_every_sensitive_action_is_audited_without_personal_data(make_client):
    staff, admin, stud = make_client("staff1"), make_client("admin1"), make_client("stud2")
    staff.get("/api/students/S001")
    staff.post("/api/decisions", json={"student_id": "S001", "opp_id": "J028", "decision": "flag", "note": "call Lakshmi 9876543210"})
    stud.post("/api/threads/student/S002/messages", json={"body": "my secret message text"})
    make_client("acme").get("/api/me/listings/J028")
    events = admin.get("/api/admin/audit?limit=500").json()
    actions = {e["action"] for e in events}
    assert {"login.ok", "login.failed", "student.view", "decision.saved", "message.sent", "listing.view"} <= actions
    blob = json.dumps(events)
    for banned in ("Lakshmi", "9876543210", "my secret message text", "call ", PASSWORD, "scrypt"):
        assert banned not in blob, banned
    assert "S001" in blob  # IDs are fine
    csv_text = admin.get("/api/admin/audit.csv").text
    assert csv_text.startswith("id,at,user_id") and "student.view" in csv_text
    assert admin.get("/api/admin/audit?action=student.view").json()[0]["action"] == "student.view"


def test_the_audit_log_cannot_be_changed_through_the_api(make_client):
    admin = make_client("admin1")
    for method in ("put", "patch", "delete"):
        assert getattr(admin, method)("/api/admin/audit").status_code in (404, 405)
    with pytest.raises(Exception, match="append-only"):
        store.connect().execute("DELETE FROM audit_log")


def test_ready_fails_when_a_pipeline_file_is_missing(make_client, monkeypatch, tmp_path):
    from matcher.config import PATHS
    monkeypatch.setitem(PATHS, "students", tmp_path / "nope.json")
    r = make_client().get("/api/ready")
    assert r.status_code == 503 and r.json() == {"ready": False, "missing": ["students"]}
    assert make_client().get("/api/health").status_code == 200  # the process itself is still up


def test_successful_sign_ins_do_not_use_up_the_address_limit(make_client):
    for _ in range(30):
        c = make_client()
        assert c.post("/api/auth/login", json={"username": "staff1", "password": PASSWORD}).status_code == 200


# ---------------- demo sign-in (pick a user, no password) ----------------

def test_demo_login_is_off_by_default(make_client):
    c = make_client()
    assert c.get("/api/auth/mode").json() == {"demo": False}
    assert c.get("/api/auth/demo-users").status_code == 404
    assert c.post("/api/auth/demo-login", json={"username": "staff1"}).status_code == 404


def test_demo_login_works_and_is_audited_when_on(make_client, monkeypatch):
    monkeypatch.setenv("DEMO_LOGIN", "1")
    c = make_client()
    assert c.get("/api/auth/mode").json() == {"demo": True}
    users = c.get("/api/auth/demo-users").json()
    assert {"staff1", "stud1", "acme"} <= {u["username"] for u in users} and "password_hash" not in json.dumps(users)
    r = c.post("/api/auth/demo-login", json={"username": "stud1"})
    assert r.status_code == 200 and r.json()["user"]["role"] == "student"
    c.headers["X-CSRF-Token"] = r.json()["csrf"]
    assert c.get("/api/me/student").json()["profile"]["student_id"] == "S001"   # real session, real role checks
    assert c.get("/api/students").status_code == 403
    assert c.post("/api/auth/demo-login", json={"username": "nobody"}).status_code == 404
    events = make_client("admin1").get("/api/admin/audit?action=login.demo").json()
    assert events and events[0]["username"] == "stud1"


def test_demo_login_skips_the_forced_password_change(make_client, monkeypatch):
    monkeypatch.setenv("DEMO_LOGIN", "1")
    accounts.create_user("fresh1", "Fresh One", "ngo_staff")  # temporary password, must change
    c = make_client()
    r = c.post("/api/auth/demo-login", json={"username": "fresh1"})
    c.headers["X-CSRF-Token"] = r.json()["csrf"]
    assert c.get("/api/students").status_code == 200


def test_demo_login_is_refused_in_secure_mode(make_client, monkeypatch):
    monkeypatch.setenv("DEMO_LOGIN", "1")
    monkeypatch.setenv("COOKIE_SECURE", "1")
    monkeypatch.setenv("CANDIDATE_SALT", "x" * 32)
    assert any("DEMO_LOGIN" in p for p in settings.check_production_ready())
    c = make_client()
    assert c.get("/api/auth/mode").json() == {"demo": False}
    assert c.post("/api/auth/demo-login", json={"username": "staff1"}).status_code == 404
    with pytest.raises(auth.AuthError):
        accounts.demo_sign_in("staff1")
