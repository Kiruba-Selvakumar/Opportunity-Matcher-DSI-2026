"""Interview scheduling, invites, notes and the notetaker. Google and Fireflies are replaced by fakes: nothing leaves."""
import hashlib
import hmac
import json
from datetime import datetime, timedelta

import pytest

from matcher import accounts, fireflies, google_calendar, ics, integrations, interviews, meeting_notes, outbox

from .test_listings_api import GOOD


@pytest.fixture(autouse=True)
def sync(monkeypatch):
    monkeypatch.setenv("OUTBOX_SYNC", "1")


def later(days=2, hour=15):
    return (datetime.now() + timedelta(days=days)).replace(hour=hour, minute=0, second=0, microsecond=0).strftime("%Y-%m-%dT%H:%M")


def shortlisted(make_client, student="pupil5", sid="S005"):
    """A listing owned by acme with one student shared and shortlisted. Returns (admin, staff, acme, stud, oid, app_id)."""
    admin, staff, acme, stud = make_client("admin1"), make_client("staff1"), make_client("acme"), make_client(student)
    accounts.set_email(accounts.get_by_username("acme").id, "hr@acme.example.com")
    oid = admin.post("/api/listings", json={**GOOD, "title": f"Interview Analyst for {student}", "owner_username": "acme"}).json()["opp_id"]
    app = stud.post("/api/me/applications", json={"opp_id": oid}).json()
    admin.post(f"/api/applications/{app['id']}/status", json={"status": "shared"})
    return admin, staff, acme, stud, oid, app["id"]


def test_time_rules():
    app = {"id": 1, "student_id": "S001", "opp_id": "J001"}
    with pytest.raises(interviews.InterviewError, match="passed"):
        interviews.parse_when("2020-01-01T10:00") and interviews.create(app, "2020-01-01T10:00", 30, "ngo", "x")
    assert interviews.parse_when("2026-12-01T15:00").utcoffset() == timedelta(hours=5, minutes=30)
    assert interviews.words("2026-12-01T15:00:00+05:30") == "Tue 1 Dec, 3:00 pm"
    assert interviews.TAG_RE.search("Interview: QA (INT-42)").group(1) == "42"


def test_ics_file():
    data = ics.event("interview-1@x", datetime.fromisoformat("2026-12-01T15:00:00+05:30"), 30, "Interview: QA, round 1", "Line one\nline two")
    text = data.decode()
    assert "DTSTART:20261201T093000Z" in text and "DTEND:20261201T100000Z" in text and "SUMMARY:Interview: QA\\, round 1" in text
    assert "METHOD:REQUEST" in text and "\r\n" in text
    assert "STATUS:CANCELLED" in ics.event("u", datetime.now().astimezone(), 30, "x", cancelled=True).decode()


def test_ngo_schedules_without_google_and_everyone_gets_a_calendar_file(make_client):
    admin, staff, acme, stud, oid, app_id = shortlisted(make_client)
    r = staff.post(f"/api/applications/{app_id}/interviews", json={"starts_at": later(), "minutes": 30, "interviewer": "employer",
                                                                   "mode": "meet", "meet_link": "https://meet.google.com/abc-defg-hij"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["calendar"] == "ics" and body["interview"]["meet_link"].endswith("abc-defg-hij")
    assert body["interview"]["interviewer_email"] == "hr@acme.example.com"
    mails = [m for m in outbox.list_items(channel="email") if m["kind"] == "interview" and m["created_at"]]
    assert mails[0]["address"] == "hr@acme.example.com" and "Candidate code" in mails[0]["body"] and "S005" not in mails[0]["body"]
    mine = next(a for a in stud.get("/api/me/applications").json() if a["id"] == app_id)
    assert mine["status"] == "interview" and mine["interviews"][0]["meet_link"].endswith("abc-defg-hij")
    assert "interviewer_email" not in mine["interviews"][0]                                     # students do not get staff emails
    emp = next(a for a in acme.get(f"/api/me/listings/{oid}").json()["applicants"] if a["id"] == app_id)
    assert emp["interviews"][0]["id"] == body["interview"]["id"] and "student_id" not in json.dumps(emp["interviews"])
    assert any("Interview for" in n["text"] for n in stud.get("/api/notifications").json()["items"])
    assert staff.get(f"/api/interviews/{body['interview']['id']}/invite.ics").headers["content-type"].startswith("text/calendar")


def test_employer_schedules_after_shortlisting_and_moves_or_cancels(make_client):
    admin, staff, acme, stud, oid, app_id = shortlisted(make_client, "pupil6", "S006")
    early = acme.post(f"/api/me/applications/{app_id}/interviews", json={"starts_at": later(), "mode": "phone"})
    assert early.status_code == 422 and "Shortlist" in early.json()["detail"]
    acme.post(f"/api/me/applications/{app_id}/status", json={"status": "shortlisted"})
    r = acme.post(f"/api/me/applications/{app_id}/interviews", json={"starts_at": later(3), "mode": "in_person", "location": ""})
    assert r.status_code == 422 and "address" in r.json()["detail"]
    r = acme.post(f"/api/me/applications/{app_id}/interviews", json={"starts_at": later(3), "mode": "phone", "interviewer": "ngo"})
    iv = r.json()["interview"]
    assert iv["interviewer"] == "employer"                                                     # an employer interviews themselves
    assert make_client("other").patch(f"/api/interviews/{iv['id']}", json={"status": "done"}).status_code == 404
    moved = acme.patch(f"/api/interviews/{iv['id']}", json={"starts_at": later(4, 11)}).json()
    assert moved["when"].endswith("11:00 am")
    gone = staff.patch(f"/api/interviews/{iv['id']}", json={"status": "cancelled"}).json()
    assert gone["status"] == "cancelled"
    assert any("cancelled" in n["text"] for n in stud.get("/api/notifications").json()["items"])
    assert iv["id"] not in [x["id"] for x in staff.get("/api/interviews").json()]


def test_pasted_notes_become_action_points_and_case_notes(make_client):
    admin, staff, acme, stud, oid, app_id = shortlisted(make_client, "stud2", "S002")
    iv = staff.post(f"/api/applications/{app_id}/interviews", json={"starts_at": later(), "mode": "phone", "interviewer": "ngo"}).json()["interview"]
    text = ("[00:01] Officer: Thanks for joining. Ravi Teja did well on SQL.\n"
            "[00:05] Employer: We will send the offer letter by Friday.\n"
            "Officer: Ravi needs to submit his marks memo. Call 9876543210 if needed.")
    got = staff.post(f"/api/interviews/{iv['id']}/notes", json={"text": text}).json()
    assert got["status"] == "done" and got["notes_source"] == "pasted (rule)"
    assert any("offer letter" in a for a in got["action_items"]) and any("marks memo" in a for a in got["action_items"])
    blob = json.dumps(got["action_items"])
    assert "Ravi" not in blob and "9876543210" not in blob                                     # names and phones are taken out
    note = staff.post(f"/api/interviews/{iv['id']}/to-case-notes", json={"follow_up_on": "2026-12-01"}).json()
    assert note["follow_up_on"] == "2026-12-01" and "offer letter" in note["body"]
    assert stud.post(f"/api/interviews/{iv['id']}/notes", json={"text": "x"}).status_code == 404


def test_rules_extract_tasks():
    out = meeting_notes.extract("Hello.\nKiran: I will share the test link tomorrow.\nNice weather today.", ["Kiran"])
    assert out["method"] == "rule" and out["action_items"] == ["I will share the test link tomorrow."]
    with pytest.raises(ValueError):
        meeting_notes.extract("   ", [])


def test_fireflies_notes_and_webhook(make_client, monkeypatch):
    admin, staff, acme, stud, oid, app_id = shortlisted(make_client, "stud1", "S001")
    iv = staff.post(f"/api/applications/{app_id}/interviews", json={
        "starts_at": later(), "mode": "meet", "meet_link": "https://meet.google.com/xyz-abcd-efg", "notetaker": True}).json()
    assert "Fireflies is not set up" in iv["warnings"][0]
    monkeypatch.setenv("FIREFLIES_API_KEY", "ff-key")
    monkeypatch.setenv("FIREFLIES_WEBHOOK_SECRET", "ff-secret")
    transcript = {"id": "T1", "title": f"Interview ({interviews.tag(iv['interview']['id'])})", "meeting_link": "https://meet.google.com/xyz-abcd-efg?pli=1",
                  "summary": {"overview": "Lakshmi Prasanna answered SQL questions well.",
                              "action_items": "**Acme HR**\nSend the assignment (02:10)\n\n**Lakshmi Prasanna**\nShare GitHub link (05:00)"}}
    calls = []

    class Fake:
        status_code = 200
        content = b"x"

        def __init__(self, data):
            self.data = data

        def json(self):
            return self.data

    def fake_http(body, key):
        calls.append(body)
        return Fake({"data": {"transcript": transcript}})
    monkeypatch.setattr(fireflies, "_http", fake_http)
    raw = json.dumps({"meetingId": "T1", "eventType": "Transcription completed"}).encode()
    c = make_client()
    assert c.post("/api/fireflies/webhook", content=raw, headers={"x-hub-signature": "nope"}).status_code == 403
    sig = hmac.new(b"ff-secret", raw, hashlib.sha256).hexdigest()
    r = c.post("/api/fireflies/webhook", content=raw, headers={"x-hub-signature": sig, "Content-Type": "application/json"})
    assert r.json() == {"ok": True, "matched": True} and calls[0]["variables"] == {"id": "T1"}
    got = interviews.get(iv["interview"]["id"])
    assert got["action_items"] == ["Send the assignment", "Share GitHub link"] and got["notes_source"] == "fireflies"
    assert "Lakshmi" not in got["summary"]                                                      # names taken out of the summary
    monkeypatch.setattr(fireflies, "_http", lambda body, key: Fake({"errors": [{"message": "Too many requests"}]}))
    r = staff.post(f"/api/interviews/{iv['interview']['id']}/notetaker")
    assert r.status_code == 422 and "Too many" in r.json()["detail"]


def test_google_event_payload_and_connection(make_client, monkeypatch):
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "cid")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "secret")
    seen = []

    class R:
        def __init__(self, code, data):
            self.status_code, self._d, self.content = code, data, b"x"

        def json(self):
            return self._d

    def fake(method, url, **kw):
        seen.append((method, url, kw))
        if url == google_calendar.TOKEN_URL:
            payload = "eyJlbWFpbCI6Im5nb0BleGFtcGxlLm9yZyJ9"                                      # {"email":"ngo@example.org"}
            return R(200, {"access_token": "a", "expires_in": 3600, "refresh_token": "r", "id_token": f"h.{payload}.s"})
        return R(200, {"id": "ev1", "hangoutLink": "https://meet.google.com/new-link-abc"})
    monkeypatch.setattr(google_calendar, "_http", fake)
    admin = make_client("admin1")
    start = admin.get("/api/integrations/google/start", follow_redirects=False)
    assert start.status_code == 303 and start.headers["location"].startswith(google_calendar.AUTH_URL)
    state = start.headers["location"].split("state=")[1].split("&")[0]
    bad = admin.get("/api/integrations/google/callback?state=forged&code=c", follow_redirects=False)
    assert "google_error" in bad.headers["location"]
    ok = admin.get(f"/api/integrations/google/callback?state={state}&code=c", follow_redirects=False)
    assert "google=connected" in ok.headers["location"] and integrations.get("google")["email"] == "ngo@example.org"
    assert make_client("staff1").get("/api/integrations/google/start", follow_redirects=False).status_code == 403

    admin2, staff, acme, stud, oid, app_id = shortlisted(make_client, "pupil4", "S004")
    r = staff.post(f"/api/applications/{app_id}/interviews", json={"starts_at": later(), "mode": "meet", "invite_student": True}).json()
    assert r["calendar"] == "google" and r["interview"]["meet_link"] == "https://meet.google.com/new-link-abc"
    method, url, kw = next(x for x in seen if x[1] == google_calendar.API)
    ev = kw["json"]
    assert kw["params"] == {"conferenceDataVersion": 1, "sendUpdates": "all"} and ev["guestsCanSeeOtherGuests"] is False
    assert ev["conferenceData"]["createRequest"]["conferenceSolutionKey"]["type"] == "hangoutsMeet"
    assert "hr@acme.example.com" in [a["email"] for a in ev["attendees"]] and len(ev["attendees"]) == 2   # employer and student
    assert "INT-" in ev["summary"] and "S004" not in json.dumps(ev)
    assert admin.post("/api/integrations/google/disconnect").json()["ok"] and integrations.get("google") is None


def test_notetaker_and_fetching_notes_succeed_with_fireflies(make_client, monkeypatch):
    admin, staff, acme, stud, oid, app_id = shortlisted(make_client, "pupil6", "S006")
    link = "https://meet.google.com/ntk-abcd-efg"
    iv = staff.post(f"/api/applications/{app_id}/interviews", json={"starts_at": later(), "mode": "meet", "meet_link": link}).json()["interview"]
    tag = interviews.tag(iv["id"])
    monkeypatch.setenv("FIREFLIES_API_KEY", "ff-key")

    class Fake:
        status_code = 200
        content = b"x"

        def __init__(self, data):
            self.data = data

        def json(self):
            return self.data

    answers = {"addToLiveMeeting": {"addToLiveMeeting": {"success": True}}, "transcripts": {"transcripts": []}}
    monkeypatch.setattr(fireflies, "_http", lambda body, key: Fake({"data": next(v for k, v in answers.items() if k in body["query"])}))
    assert staff.post(f"/api/interviews/{iv['id']}/notetaker").json() == {"ok": True}
    r = staff.post(f"/api/interviews/{iv['id']}/fetch-notes")
    assert r.status_code == 404 and "no transcript" in r.json()["detail"]
    answers["transcripts"] = {"transcripts": [{"id": "T9", "title": f"Interview ({tag})", "meeting_link": link,
                                               "summary": {"overview": "It went well.", "action_items": "Send the assignment (02:10)"}}]}
    r = staff.post(f"/api/interviews/{iv['id']}/fetch-notes")
    assert r.status_code == 200 and r.json()["summary"] == "It went well." and r.json()["action_items"] == ["Send the assignment"]
    assert acme.post(f"/api/interviews/{iv['id']}/fetch-notes").status_code == 403


def test_a_refused_interview_leaves_the_application_where_it_was(make_client):
    from matcher import applications
    admin, staff, acme, stud, oid, app_id = shortlisted(make_client, "pupil4", "S004")
    r = staff.post(f"/api/applications/{app_id}/interviews", json={"starts_at": "2020-01-01T10:00", "mode": "phone", "interviewer": "ngo"})
    assert r.status_code == 422 and "passed" in r.json()["detail"]
    r = staff.post(f"/api/applications/{app_id}/interviews", json={"starts_at": later(), "mode": "in_person", "location": " "})
    assert r.status_code == 422 and "address" in r.json()["detail"]
    assert applications.get(app_id)["status"] == "shared" and interviews.list_for(application_id=app_id) == []
    r = staff.post(f"/api/applications/{app_id}/interviews", json={"starts_at": later(), "mode": "phone", "interviewer": "ngo"})
    assert r.status_code == 200 and applications.get(app_id)["status"] == "interview"


def test_fireflies_find_wants_the_exact_interview_tag(monkeypatch):
    monkeypatch.setenv("FIREFLIES_API_KEY", "ff-key")
    other = {"id": "T12", "title": "Interview: QA (INT-12)", "meeting_link": "https://meet.google.com/aaa-bbbb-ccc"}
    mine = {"id": "T1", "title": "Interview: QA (INT-1)", "meeting_link": "https://meet.google.com/zzz-yyyy-xxx"}
    renamed = {"id": "T3", "title": "Renamed call", "meeting_link": "https://meet.google.com/zzz-yyyy-xxx"}
    found = []

    class Fake:
        status_code = 200
        content = b"x"

        def json(self):
            return {"data": {"transcripts": found}}
    monkeypatch.setattr(fireflies, "_http", lambda body, key: Fake())
    found[:] = [other]
    assert fireflies.find(None, "INT-1") is None                                               # INT-12 is another interview
    assert fireflies.find("https://meet.google.com/aaa-bbbb-ccc", "INT-1") is None              # same link, but tagged for INT-12
    found[:] = [other, mine]
    assert fireflies.find(None, "INT-1")["id"] == "T1"
    found[:] = [renamed]
    assert fireflies.find("https://meet.google.com/zzz-yyyy-xxx/", "INT-1")["id"] == "T3"      # no tag: the link decides


def test_fetched_notes_go_to_the_interview_asked_for(make_client, monkeypatch):
    admin, staff, acme, stud, oid, app_id = shortlisted(make_client, "stud1", "S001")
    link = "https://meet.google.com/rpt-abcd-efg"                                              # one Meet room used twice
    first = staff.post(f"/api/applications/{app_id}/interviews", json={"starts_at": later(), "mode": "meet", "meet_link": link}).json()["interview"]
    second = staff.post(f"/api/applications/{app_id}/interviews", json={"starts_at": later(3), "mode": "meet", "meet_link": link}).json()["interview"]
    monkeypatch.setenv("FIREFLIES_API_KEY", "ff-key")
    t = {"id": "T7", "title": f"Interview ({interviews.tag(first['id'])})", "meeting_link": link,
         "summary": {"overview": "First round went well.", "action_items": "Send the assignment"}}

    class Fake:
        status_code = 200
        content = b"x"

        def json(self):
            return {"data": {"transcripts": [t]}}
    monkeypatch.setattr(fireflies, "_http", lambda body, key: Fake())
    r = staff.post(f"/api/interviews/{first['id']}/fetch-notes")
    assert r.status_code == 200 and r.json()["id"] == first["id"]
    assert interviews.get(first["id"])["summary"] == "First round went well."
    assert interviews.get(second["id"])["summary"] is None and interviews.get(second["id"])["status"] == "scheduled"


@pytest.fixture
def fake_google(monkeypatch):
    """Google connected, with every call answered here. move_ok decides whether moving an event works."""
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "cid")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "secret")
    monkeypatch.setitem(google_calendar._token, "value", None)
    box = {"move_ok": True, "calls": []}

    class R:
        def __init__(self, code, data):
            self.status_code, self._d, self.content = code, data, b"x"

        def json(self):
            return self._d

    def fake(method, url, **kw):
        box["calls"].append(method)
        if url == google_calendar.TOKEN_URL:
            return R(200, {"access_token": "a", "expires_in": 3600})
        if method == "PATCH" and not box["move_ok"]:
            return R(403, {"error": {"message": "Rate limit exceeded"}})
        return R(200, {"id": "ev9", "hangoutLink": "https://meet.google.com/gen-erat-edx"})
    monkeypatch.setattr(google_calendar, "_http", fake)
    integrations.put("google", {"refresh_token": "r", "email": "ngo@example.org"}, "admin1")
    yield box
    integrations.remove("google")
    google_calendar._token.update(value=None, expires=0.0)


def test_a_move_google_refuses_changes_nothing(make_client, fake_google):
    admin, staff, acme, stud, oid, app_id = shortlisted(make_client, "pupil5", "S005")
    made = staff.post(f"/api/applications/{app_id}/interviews", json={"starts_at": later(), "mode": "meet"}).json()
    assert made["calendar"] == "google"
    iv = interviews.get(made["interview"]["id"])

    def moves():
        return [n for n in stud.get("/api/notifications").json()["items"] if "moved to" in n["text"]]
    told = len(moves())
    fake_google["move_ok"] = False
    r = staff.patch(f"/api/interviews/{iv['id']}", json={"starts_at": later(4, 11)})
    assert r.status_code == 422 and "Rate limit" in r.json()["detail"]
    kept = interviews.get(iv["id"])
    assert kept["starts_at"] == iv["starts_at"] and kept["sequence"] == iv["sequence"] and len(moves()) == told
    fake_google["calls"].clear()
    r = staff.patch(f"/api/interviews/{iv['id']}", json={"starts_at": "2020-01-01T10:00"})
    assert r.status_code == 422 and "passed" in r.json()["detail"] and "PATCH" not in fake_google["calls"]
    fake_google["move_ok"] = True
    moved = staff.patch(f"/api/interviews/{iv['id']}", json={"starts_at": later(4, 11)})
    assert moved.status_code == 200 and moved.json()["when"].endswith("11:00 am")
    assert interviews.get(iv["id"])["sequence"] == iv["sequence"] + 1


def test_a_cancelled_interview_stays_cancelled(make_client):
    admin, staff, acme, stud, oid, app_id = shortlisted(make_client, "pupil6", "S006")
    iv = staff.post(f"/api/applications/{app_id}/interviews", json={"starts_at": later(), "mode": "phone", "interviewer": "ngo"}).json()["interview"]
    assert staff.patch(f"/api/interviews/{iv['id']}", json={"status": "cancelled"}).json()["status"] == "cancelled"
    for change in ({"status": "scheduled"}, {"status": "done"}, {"starts_at": later(5)}, {"status": "cancelled"}):
        r = staff.patch(f"/api/interviews/{iv['id']}", json=change)
        assert r.status_code == 422 and "cancelled" in r.json()["detail"], change
    assert interviews.get(iv["id"])["status"] == "cancelled"
