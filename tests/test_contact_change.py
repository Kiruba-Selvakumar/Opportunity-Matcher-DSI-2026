"""A student asks for a new mobile number and NGO staff confirm it before anything uses it."""
import json

from matcher import audit, contacts


def test_a_number_change_waits_for_the_ngo_and_never_leaks(make_client):
    stud, staff, acme, other = make_client("stud2"), make_client("staff1"), make_client("acme"), make_client("pupil4")
    old = contacts.phone("S002")
    me = stud.get("/api/me/contact").json()
    assert me["phone"].endswith(old[-4:]) and old not in json.dumps(me) and me["pending"] is None   # only the last four digits

    for bad in ("12345", "5876543210", "call me"):
        assert stud.post("/api/me/contact-change", json={"phone": bad}).status_code == 422
    assert stud.post("/api/me/contact-change", json={"phone": old[2:]}).status_code == 422          # already theirs
    assert stud.post("/api/me/contact-change", json={"phone": contacts.phone("S004")[2:]}).status_code == 422   # someone else's

    me = stud.post("/api/me/contact-change", json={"phone": "98765 01234"}).json()
    assert me["pending"]["phone"].endswith("1234") and "9876501234" not in json.dumps(me)
    assert contacts.phone("S002") == old                                                             # not used yet

    for c in (stud, acme, other):
        assert c.get("/api/contact-changes").status_code == 403
    waiting = staff.get("/api/contact-changes?student_id=S002").json()
    assert len(waiting) == 1 and waiting[0]["phone"] == "919876501234"                              # staff see it in full
    assert "S002" in staff.get("/api/dashboard").json()["attention"]["number_changes"]

    r = staff.post(f"/api/contact-changes/{waiting[0]['id']}/decision",
                   json={"approve": False, "note": "We called 9876501234 and nobody answered."}).json()
    assert r["status"] == "rejected" and contacts.phone("S002") == old
    last = stud.get("/api/me/contact").json()["last"]
    assert last["status"] == "rejected" and "9876501234" not in (last["note"] or "")                # the note is redacted
    assert staff.post(f"/api/contact-changes/{waiting[0]['id']}/decision", json={"approve": True}).status_code == 404

    stud.post("/api/me/contact-change", json={"phone": "+91 98765 01234"})
    cid = staff.get("/api/contact-changes?student_id=S002").json()[0]["id"]
    staff.post(f"/api/contact-changes/{cid}/decision", json={"approve": True})
    assert contacts.phone("S002") == "919876501234" and contacts.student_by_phone("9876501234") == "S002"
    assert contacts.student_by_phone(old) is None                                                    # the old number no longer maps to them
    assert stud.get("/api/me/contact").json()["phone"].endswith("1234")
    assert any("new mobile number" in n["text"] for n in stud.get("/api/notifications").json()["items"])

    trail = [e for e in audit.list_events(limit=5000) if e["action"].startswith("contact.")]
    assert {e["action"] for e in trail} >= {"contact.change_requested", "contact.change_decided"}
    blob = json.dumps(trail)
    assert "9876501234" not in blob and old not in blob and old[2:] not in blob                     # never a number in the log
