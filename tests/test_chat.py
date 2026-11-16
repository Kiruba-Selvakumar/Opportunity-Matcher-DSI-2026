import pytest
from pydantic import ValidationError

from matcher import chat


def msg(**kw):
    base = dict(thread_type="student", thread_id="S001", sender_role="student", body="Hello")
    base.update(kw)
    return chat.Message(**base)


def test_validation():
    with pytest.raises(ValidationError):
        msg(body="   ")
    with pytest.raises(ValidationError):
        msg(body="x" * 2001)
    with pytest.raises(ValidationError):
        msg(sender_role="lister")  # a lister cannot post in a student thread
    with pytest.raises(ValidationError):
        msg(thread_type="listing", thread_id="J001", sender_role="student")
    assert msg(thread_type="listing", thread_id="J001", sender_role="lister").sender_role == "lister"


def test_post_list_and_read_flow(tmp_path):
    p = tmp_path / "c.db"
    chat.post_message(msg(body="Is the Hyderabad job remote?"), p)
    chat.post_message(msg(sender_role="ngo", body="No, it is onsite."), p)
    assert [m.sender_role for m in chat.list_messages("student", "S001", p)] == ["student", "ngo"]
    assert chat.unread_total(p) == 1            # NGO has not read the student's message
    assert chat.mark_read("student", "S001", "ngo", p) == 1
    assert chat.unread_total(p) == 0
    assert chat.mark_read("student", "S001", "student", p) == 1  # the NGO reply is unread by the student
    t = chat.list_threads(p)
    assert t[0]["count"] == 2 and t[0]["last_role"] == "ngo"


def test_threads_are_separate_and_sorted(tmp_path):
    p = tmp_path / "c.db"
    chat.post_message(msg(thread_id="S001"), p)
    chat.post_message(msg(thread_type="listing", thread_id="J001", sender_role="lister"), p)
    chat.post_message(msg(thread_id="S002"), p)
    ids = [t["thread_id"] for t in chat.list_threads(p)]
    assert ids == ["S002", "J001", "S001"]


def test_contact_details_redacted(tmp_path):
    p = tmp_path / "c.db"
    m = chat.post_message(msg(body="Call me on 9876543210 or a@b.com. Lakshmi here."), p, ["Lakshmi Prasanna"])
    assert "9876543210" not in m.body and "a@b.com" not in m.body and "Lakshmi" not in m.body


def test_api_student_thread(make_client):
    staff, stud = make_client("staff1"), make_client("stud1")
    url = "/api/threads/student/S001/messages"
    assert stud.post(url, json={"body": ""}).status_code == 422
    r = stud.post(url, json={"body": "Can I ask about J028?", "about_opp_id": "J028"})
    assert r.status_code == 200 and r.json()["about_opp_id"] == "J028" and r.json()["sender_role"] == "student"
    assert stud.post(url, json={"body": "x", "about_opp_id": "ZZ"}).status_code == 404
    thread = lambda: next(t for t in staff.get("/api/threads").json() if t["thread_id"] == "S001")  # noqa: E731
    assert thread()["unread"] >= 1
    assert any(m["body"] == "Can I ask about J028?" for m in staff.get(url).json())  # opening the thread marks it read
    assert thread()["unread"] == 0
    staff.post(url, json={"body": "Yes, go ahead."})
    assert "S001" in [t["thread_id"] for t in staff.get("/api/threads").json()]


def test_ngo_message_notifies_the_other_side(make_client):
    staff, stud, acme = make_client("staff1"), make_client("stud1"), make_client("acme")
    unread = lambda c: c.get("/api/notifications").json()["unread"]  # noqa: E731
    before = unread(stud)
    stud.post("/api/threads/student/S001/messages", json={"body": "Any news on my application?"})
    assert unread(stud) == before                               # your own message is not news to you
    staff.post("/api/threads/student/S001/messages", json={"body": "Yes, please call the office."})
    assert unread(stud) == before + 1
    note = stud.get("/api/notifications").json()["items"][0]
    assert note["link"] == "/student/messages" and "call the office" not in note["text"]    # never the message itself
    before, other = unread(acme), unread(make_client("other"))
    staff.post("/api/threads/listing/J028/messages", json={"body": "Can you confirm the pay?"})
    assert unread(acme) == before + 1 and unread(make_client("other")) == other
    assert acme.get("/api/notifications").json()["items"][0]["link"] == "/employer/messages?listing=J028"


def test_api_listing_thread(make_client):
    acme, staff = make_client("acme"), make_client("staff1")
    url = "/api/threads/listing/J028/messages"
    assert acme.post(url, json={"body": "We need 3 hires."}).json()["sender_role"] == "lister"
    assert staff.post(url, json={"body": "Noted."}).json()["sender_role"] == "ngo"
    assert staff.get("/api/threads/bogus/J028/messages").status_code == 404
