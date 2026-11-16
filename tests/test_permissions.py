"""Who may call what. One signed-in client per role, and a signed-out one."""
import json
import re

import pytest

NGO_GETS = ["/api/students", "/api/students/S001", "/api/students/S001/raw", "/api/students/S001/matches",
            "/api/contacts", "/api/contacts/S001", "/api/config", "/api/opportunities", "/api/opportunities/J028",
            "/api/decisions", "/api/decisions.csv", "/api/threads", "/api/threads/unread"]
ADMIN_GETS = ["/api/admin/users", "/api/admin/audit", "/api/admin/audit.csv"]
POSTS = [("/api/students/S001/whatif", {"can_relocate": "yes"}),
         ("/api/decisions", {"student_id": "S001", "opp_id": "J028", "decision": "accept"}),
         ("/api/admin/users", {"username": "zzz999", "display_name": "Z", "role": "ngo_staff"})]


@pytest.mark.parametrize("path", NGO_GETS + ADMIN_GETS + ["/api/me/student", "/api/me/listings", "/api/auth/me"])
def test_signed_out_gets_401(make_client, path):
    assert make_client().get(path).status_code == 401


def test_signed_out_cannot_post(make_client):
    c = make_client()
    for path, body in POSTS:
        assert c.post(path, json=body).status_code == 401


@pytest.mark.parametrize("who", ["stud1", "acme"])
@pytest.mark.parametrize("path", NGO_GETS + ADMIN_GETS)
def test_students_and_employers_cannot_use_ngo_endpoints(make_client, who, path):
    assert make_client(who).get(path).status_code == 403


@pytest.mark.parametrize("who", ["stud1", "acme", "staff1"])
@pytest.mark.parametrize("path,body", POSTS[:2] + [POSTS[2]])
def test_only_the_right_roles_can_post(make_client, who, path, body):
    r = make_client(who).post(path, json=body)
    if path == "/api/admin/users" or who != "staff1":
        assert r.status_code == 403
    else:
        assert r.status_code == 200


def test_staff_cannot_use_admin_endpoints_but_admin_can(make_client):
    assert make_client("staff1").get("/api/admin/users").status_code == 403
    assert make_client("admin1").get("/api/admin/users").status_code == 200
    assert make_client("admin1").get("/api/students").status_code == 200  # admin is staff plus


def test_ngo_cannot_use_the_student_or_employer_endpoints(make_client):
    c = make_client("staff1")
    assert c.get("/api/me/student").status_code == 403
    assert c.get("/api/me/listings").status_code == 403


# ---------------- students see only themselves ----------------

def test_student_sees_own_data_and_nothing_else(make_client):
    c = make_client("stud1")
    r = c.get("/api/me/student")
    assert r.status_code == 200
    d = r.json()
    assert d["profile"]["student_id"] == "S001" and d["name"] == "Lakshmi Prasanna"
    blob = json.dumps(d)
    assert not re.search(r"\bS(?!001\b)\d{3}\b", blob)           # no other student ID anywhere
    assert all("breakdown" not in m for m in d["matches"])        # no staff scoring internals
    assert "phone" not in blob and "@example.com" not in blob
    # a different student gets a different, own payload
    assert make_client("stud2").get("/api/me/student").json()["profile"]["student_id"] == "S002"


def test_student_cannot_read_another_students_thread(make_client):
    c = make_client("stud1")
    assert c.get("/api/threads/student/S001/messages").status_code == 200
    assert c.get("/api/threads/student/S002/messages").status_code == 404
    assert c.post("/api/threads/student/S002/messages", json={"body": "hi"}).status_code == 404
    assert c.get("/api/threads/listing/J028/messages").status_code == 404


# ---------------- employers see only their listings, anonymously ----------------

def test_employer_sees_only_own_listings(make_client):
    c = make_client("acme")
    ids = [x["opp_id"] for x in c.get("/api/me/listings").json()]
    assert "J028" in ids and "J027" not in ids and all(i == "J028" or i.startswith("E") for i in ids)   # only their own
    assert c.get("/api/me/listings/J028").status_code == 200
    assert c.get("/api/me/listings/J027").status_code == 404          # another employer's listing
    assert c.get("/api/me/listings/J001").status_code == 404          # not theirs
    assert c.get("/api/threads/listing/J027/messages").status_code == 404
    assert c.get("/api/threads/listing/J028/messages").status_code == 200
    assert make_client("other").get("/api/me/listings/J027").status_code == 200


def test_employer_response_has_no_personal_or_private_fields(make_client):
    staff = make_client("staff1")
    names = list(staff.get("/api/contacts").json().values())
    codes = {s["candidate_code"]: s["id"] for s in staff.get("/api/students").json()}
    d = make_client("acme").get("/api/me/listings/J028").json()
    blob = json.dumps(d)
    assert d["candidates"] and all(re.fullmatch(r"[0-9a-f]{8}", c["candidate_code"]) for c in d["candidates"])
    for banned in ("student_id", "budget", "family_limits", "can_relocate", "concerns", "removed_by", "checks", "needs_move"):
        assert banned not in blob, banned
    assert not re.search(r"\bS\d{3}\b", blob)
    assert not any(n.split()[0] in blob for n in names)
    # staff can turn a code back into a student
    assert all(c["candidate_code"] in codes for c in d["candidates"])


def test_employer_codes_depend_on_the_salt(make_client, monkeypatch):
    a = make_client("acme").get("/api/me/listings/J028").json()["candidates"][0]["candidate_code"]
    monkeypatch.setenv("CANDIDATE_SALT", "a-completely-different-salt")
    b = make_client("acme").get("/api/me/listings/J028").json()["candidates"][0]["candidate_code"]
    assert a != b


# ---------------- messages use the account's role ----------------

def test_client_cannot_choose_its_message_role(make_client):
    r = make_client("stud1").post("/api/threads/student/S001/messages", json={"body": "hi", "sender_role": "ngo"})
    assert r.status_code == 200 and r.json()["sender_role"] == "student"
    r = make_client("acme").post("/api/threads/listing/J028/messages", json={"body": "hi", "sender_role": "ngo"})
    assert r.json()["sender_role"] == "lister"


# ---------------- the new endpoints, in the same matrix ----------------

NEW_NGO_GETS = ["/api/listings/review", "/api/applications", "/api/dashboard", "/api/followups",
                "/api/students/S001/notes", "/api/students/S001/timeline"]
NEW_STUDENT_GETS = ["/api/me/applications", "/api/me/saved", "/api/me/profile", "/api/me/export"]
NEW_ANY_GETS = ["/api/notifications", "/api/auth/sessions", "/api/skills"]


@pytest.mark.parametrize("path", NEW_NGO_GETS + NEW_STUDENT_GETS + NEW_ANY_GETS)
def test_new_endpoints_need_a_sign_in(make_client, path):
    assert make_client().get(path).status_code == 401


@pytest.mark.parametrize("who", ["stud1", "acme"])
@pytest.mark.parametrize("path", NEW_NGO_GETS)
def test_new_ngo_endpoints_are_closed_to_students_and_employers(make_client, who, path):
    assert make_client(who).get(path).status_code == 403


@pytest.mark.parametrize("who", ["staff1", "admin1", "acme"])
@pytest.mark.parametrize("path", NEW_STUDENT_GETS)
def test_student_only_endpoints_are_closed_to_everyone_else(make_client, who, path):
    assert make_client(who).get(path).status_code == 403


@pytest.mark.parametrize("who", ["stud1", "staff1", "admin1", "acme"])
@pytest.mark.parametrize("path", NEW_ANY_GETS)
def test_every_signed_in_role_can_use_the_shared_endpoints(make_client, who, path):
    assert make_client(who).get(path).status_code == 200


def test_new_writes_are_closed_to_the_wrong_role(make_client):
    stud, acme, staff = make_client("stud1"), make_client("acme"), make_client("staff1")
    writes = [("post", "/api/me/applications", {"opp_id": "J001"}, [acme, staff]),
              ("put", "/api/me/profile", {"budget": 1}, [acme, staff]),
              ("post", "/api/applications/1/status", {"status": "shared"}, [stud, acme]),
              ("post", "/api/me/applications/1/status", {"status": "shortlisted"}, [stud, staff]),
              ("post", "/api/students/S001/notes", {"body": "x"}, [stud, acme]),
              ("put", "/api/me/saved/J001", None, [acme, staff])]
    for method, path, body, clients in writes:
        for c in clients:
            r = getattr(c, method)(path, json=body) if body is not None else getattr(c, method)(path)
            assert r.status_code == 403, (method, path)
    for method, path, body in [("post", "/api/me/applications", {"opp_id": "J001"}), ("put", "/api/me/profile", {"budget": 1})]:
        assert getattr(make_client(), method)(path, json=body).status_code == 401
