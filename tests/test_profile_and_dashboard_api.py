import json
import re

from .test_api import make_pdf
from .test_listings_api import approve, post


def test_a_student_edits_their_profile_and_the_matches_follow(make_client):
    stud, staff = make_client("stud1"), make_client("staff1")
    can_take = lambda: sum(i["eligible"] for i in stud.get("/api/me/browse").json())  # noqa: E731
    before = can_take()
    r = stud.put("/api/me/profile", json={"can_relocate": "yes", "budget": 15000, "family_limits": []})
    assert r.status_code == 200 and set(r.json()["edited_fields"]) == {"can_relocate", "budget", "family_limits"}
    assert can_take() > before                                                                      # re-scored at once: more listings are open to her
    assert staff.get("/api/students/S001").json()["edited_fields"] == ["can_relocate", "budget", "family_limits"]
    assert next(s for s in staff.get("/api/students").json() if s["id"] == "S001")["edited"]
    stud.put("/api/me/profile", json={"can_relocate": "no", "budget": 3000, "family_limits": ["near_home_only"]})   # put it back


def test_profile_validation_and_limits(make_client):
    stud = make_client("stud1")
    for bad in ({"can_relocate": "maybe"}, {"budget": -5}, {"cgpa": 9.9}, {"branch": "ECE"}, {"family_limits": ["x"]},
                {"extra_skills": ["Underwater Basket Weaving"]}, {}):
        assert stud.put("/api/me/profile", json=bad).status_code == 422, bad
    assert make_client("staff1").put("/api/me/profile", json={"budget": 1}).status_code == 403
    assert make_client("acme").get("/api/me/profile").status_code == 403


def test_completeness_says_what_is_missing(make_client):
    d = make_client("stud2").get("/api/me/profile").json()["completeness"]
    assert 0 <= d["percent"] <= 100 and {i["field"] for i in d["items"]} >= {"can_relocate", "budget", "skills"}
    assert all(isinstance(i["done"], bool) and i["impact"] >= 0 for i in d["items"])


def test_resume_suggestions_are_not_saved_until_chosen(make_client):
    stud = make_client("pupil5")
    pdf = make_pdf(["Skills: Kotlin, Flutter, TypeScript, Docker", "CGPA: 8.0"])
    r = stud.post("/api/me/resume", files={"file": ("cv.pdf", pdf, "application/pdf")})
    assert r.status_code == 200 and {"Kotlin", "Flutter", "Docker"} <= set(r.json()["suggested"])
    assert "Kotlin" not in stud.get("/api/me/profile").json()["profile"]["skills"]                  # nothing added yet
    stud.put("/api/me/profile", json={"extra_skills": ["Kotlin", "Flutter"]})
    skills = stud.get("/api/me/profile").json()["profile"]["skills"]
    assert "Kotlin" in skills and "Docker" not in skills
    assert stud.post("/api/me/resume", files={"file": ("cv.txt", b"hello", "text/plain")}).status_code == 422
    stud.put("/api/me/profile", json={"extra_skills": []})


def test_export_holds_only_my_data(make_client):
    stud = make_client("stud1")
    r = stud.get("/api/me/export")
    assert r.status_code == 200 and "attachment" in r.headers["content-disposition"]
    blob = r.text
    d = json.loads(blob)
    assert d["profile"]["student_id"] == "S001" and d["name"] == "Lakshmi Prasanna" and d["account"]["username"] == "stud1"
    assert not re.search(r"\bS(?!001\b)\d{3}\b", blob)
    assert make_client("acme").get("/api/me/export").status_code == 403


def test_readable_export_is_html_with_names_not_codes(make_client):
    stud = make_client("stud1")
    stud.put("/api/me/saved/J028", json={})
    sent = stud.post("/api/threads/student/S001/messages",
                     json={"body": "<script>alert(1)</script> Is this still open?", "about_opp_id": "J028"})
    assert sent.status_code == 200
    r = stud.get("/api/me/export?format=html")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/html")
    assert "my-data.html" in r.headers["content-disposition"]
    page = r.text
    assert "Lakshmi Prasanna" in page and "Data Analyst Trainee, Gopuram Software" in page   # listing ids become titles
    assert "<script>" not in page and "&lt;script&gt;" in page                                   # message text is escaped
    assert "near_home_only" not in page and "Near home only" in page and "parse_method" not in page
    assert not re.search(r"\bS(?!001\b)\d{3}\b", page)                                           # nobody else's data
    assert stud.get("/api/me/export?format=pdf").status_code == 422
    stud.delete("/api/me/saved/J028")


def test_export_html_dates_are_readable():
    from matcher.export_html import when
    assert when("2026-10-14T09:37:41+00:00") == "14 Oct 2026, 3:07 pm"
    assert when("2026-10-14T20:00:00+00:00", with_time=False) == "15 Oct 2026"
    assert when(None) == ""


def test_export_html_rupees_use_indian_grouping():
    from matcher.export_html import rupees
    assert [rupees(n) for n in (0, 3000, 150000, 12345678)] == ["Rs 0", "Rs 3,000", "Rs 1,50,000", "Rs 1,23,45,678"]


def test_case_notes_follow_ups_and_timeline(make_client):
    staff, stud = make_client("staff1"), make_client("stud1")
    n = staff.post("/api/students/S001/notes", json={"body": "Spoke to her. Call 9876543210 after exams.", "follow_up_on": "2020-01-01"}).json()
    assert "9876543210" not in n["body"] and n["author"] == "staff1"
    assert staff.post("/api/students/S001/notes", json={"body": "x", "follow_up_on": "soon"}).status_code == 422
    assert staff.post("/api/students/S001/notes", json={"body": "  "}).status_code == 422
    assert any(f["id"] == n["id"] for f in staff.get("/api/dashboard").json()["attention"]["followups"])
    assert staff.post(f"/api/notes/{n['id']}/done").status_code == 200
    assert not any(f["id"] == n["id"] for f in staff.get("/api/dashboard").json()["attention"]["followups"])
    kinds = {e["kind"] for e in staff.get("/api/students/S001/timeline").json()}
    assert "note" in kinds
    assert stud.get("/api/students/S001/notes").status_code == 403                                  # notes are NGO only
    assert stud.get("/api/students/S001/timeline").status_code == 403
    assert staff.get("/api/students/NOPE/notes").status_code == 404


def test_dashboard_numbers(make_client, monkeypatch):
    staff, acme = make_client("staff1"), make_client("acme")
    d0 = staff.get("/api/dashboard").json()
    post(acme)
    d1 = staff.get("/api/dashboard").json()
    assert d1["counts"]["pending_reviews"] == d0["counts"]["pending_reviews"] + 1
    assert d1["counts"]["students"] == 100 and d1["counts"]["active_listings"] >= 50
    assert set(d1["funnel"]) == {"interested", "shared", "shortlisted", "interview", "offered", "hired"}
    assert {"no_matches", "missing_info", "stale", "busiest", "followups", "interviews", "closing", "number_changes"} == set(d1["attention"])
    assert {"put_forward", "interviews_week", "closing_soon", "new_leads", "with_resume"} <= set(d1["counts"])
    assert make_client("stud1").get("/api/dashboard").status_code == 403
    assert make_client("acme").get("/api/dashboard").status_code == 403


def test_notifications_are_private_and_can_be_marked_read(make_client):
    acme, staff, stud = make_client("acme"), make_client("admin1"), make_client("stud2")      # new listings go to the admins
    post(acme)
    items = staff.get("/api/notifications").json()["items"]
    assert items and all("@" not in i["text"] and not re.search(r"\d{10}", i["text"]) for i in items)
    first = items[0]
    assert stud.post(f"/api/notifications/{first['id']}/read").status_code == 404                  # not theirs
    assert staff.post(f"/api/notifications/{first['id']}/read").status_code == 200
    assert staff.post("/api/notifications/read-all").status_code == 200
    assert staff.get("/api/notifications").json()["unread"] == 0
    assert make_client().get("/api/notifications").status_code == 401


def test_sessions_list_and_sign_out_everywhere_else(make_client):
    a = make_client("staff1")
    b = make_client("staff1")
    s = a.get("/api/auth/sessions").json()
    assert len(s) >= 2 and sum(x["current"] for x in s) == 1 and set(s[0]) == {"created_at", "last_seen_at", "ip", "current"}
    assert a.post("/api/auth/sessions/revoke-others").json()["revoked"] >= 1
    assert b.get("/api/auth/me").status_code == 401
    assert a.get("/api/auth/me").status_code == 200


def test_skill_list_is_open_to_signed_in_users_only(make_client):
    assert make_client().get("/api/skills").status_code == 401
    assert "Python" in make_client("stud1").get("/api/skills").json()


def test_readable_export_shows_the_stored_resume_but_never_its_text():
    from matcher.export_html import render
    base = {"account": {"username": "s1", "display_name": "Asha"}, "name": "Asha K",
            "profile": {"student_id": "S001", "branch": "CSE", "college_town": "Khammam", "grad_year": 2026, "skills": []},
            "applications": [], "saved": [], "messages": []}
    none = render({**base, "resume": None}, {})
    assert "We do not hold a resume for you." in none
    cv = {"uploaded_at": "2026-11-10T05:00:00+00:00", "source": "bulk", "pages": 2, "score": 72, "grade": "Fair",
          "skills": ["Python", "SQL"], "tips": ["Add a <b>projects</b> section"], "parts": {}, "sections": []}
    page = render({**base, "resume": cv}, {})
    assert "72 (Fair)" in page and "NGO staff (bulk upload)" in page and "10 Nov 2026" in page and "Python, SQL" in page
    assert "<b>projects</b>" not in page and "&lt;b&gt;projects&lt;/b&gt;" in page                    # tips are escaped
