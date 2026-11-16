"""Email, WhatsApp broadcasts, consent, the webhook and employer leads. Nothing leaves the machine: no keys are set,
so every message is a dry run in the outbox, and the Meta call is replaced where a test needs it."""
import hashlib
import hmac
import json

import pytest

from matcher import broadcast, contacts, leads, outbox, whatsapp

from .test_listings_api import GOOD


@pytest.fixture(autouse=True)
def sync(monkeypatch):
    monkeypatch.setenv("OUTBOX_SYNC", "1")


def test_mask_and_phone_rules():
    assert outbox.mask("ravi.t@example.com") == "r***@example.com"
    assert outbox.mask("919876543210") == "********3210"
    assert contacts.normalize_phone("98765 43210") == "919876543210"
    assert contacts.normalize_phone("+91-98765-43210") == "919876543210"
    assert contacts.normalize_phone("09876543210") == "919876543210"
    assert contacts.normalize_phone("12345") is None and contacts.normalize_phone("5876543210") is None


def test_payloads_and_signature():
    t = whatsapp.template_payload("919876543210", "new_opportunity", "en", ["QA Intern", "Acme", "30 Nov 2026", "https://x/y"])
    assert t["type"] == "template" and t["template"]["name"] == "new_opportunity"
    assert [p["text"] for p in t["template"]["components"][0]["parameters"]] == ["QA Intern", "Acme", "30 Nov 2026", "https://x/y"]
    raw = b'{"entry": []}'
    sig = "sha256=" + hmac.new(b"s3cret", raw, hashlib.sha256).hexdigest()
    assert whatsapp.verify_signature(raw, sig, "s3cret")
    assert not whatsapp.verify_signature(raw, sig, "other") and not whatsapp.verify_signature(raw, None, "s3cret")
    assert not whatsapp.verify_signature(raw, sig, "")


def test_parse_webhook():
    payload = {"entry": [{"changes": [{"value": {
        "contacts": [{"wa_id": "919000000001", "profile": {"name": "Kaveri HR"}}],
        "messages": [{"from": "919000000001", "id": "wamid.1", "type": "text", "text": {"body": "Hiring 2 testers"}},
                     {"from": "919000000001", "id": "wamid.2", "type": "image"}],
        "statuses": [{"id": "wamid.out", "status": "failed", "errors": [{"title": "Re-engagement message"}]}]}}]}]}
    msgs, stats = whatsapp.parse_webhook(payload)
    assert msgs[0] == {"from": "919000000001", "id": "wamid.1", "text": "Hiring 2 testers", "name": "Kaveri HR", "timestamp": None}
    assert "image message" in msgs[1]["text"]
    assert stats == [{"id": "wamid.out", "status": "failed", "error": "Re-engagement message"}]


def test_outbox_status_only_moves_forward(pipeline_dir):
    oid = outbox.add("whatsapp", "test", "student:S001", "****1234", "hello")
    outbox.mark(oid, "sent", provider_id="wamid.forward")
    assert outbox.update_by_provider_id("wamid.forward", "read")
    assert not outbox.update_by_provider_id("wamid.forward", "delivered")        # read is already further along
    assert outbox.update_by_provider_id("wamid.forward", "failed")
    assert next(m for m in outbox.list_items() if m["id"] == oid)["status"] == "failed"


def test_a_real_send_goes_to_meta_and_records_the_id(pipeline_dir, monkeypatch):
    sent = []
    monkeypatch.setenv("WHATSAPP_TOKEN", "t")
    monkeypatch.setenv("WHATSAPP_PHONE_NUMBER_ID", "123")
    monkeypatch.setattr(whatsapp, "_post", lambda cfg, payload: sent.append((cfg["phone_number_id"], payload)) or "wamid.real")
    contacts.set_opt_in("S001", True, "test")
    oid = whatsapp.send_template("S001", "matches", ["3", "QA Intern", "https://x"], "preview text")
    row = next(m for m in outbox.list_items() if m["id"] == oid)
    assert row["status"] == "sent" and row["provider_id"] == "wamid.real" and row["address"].endswith(contacts.phone("S001")[-4:])
    assert sent[0][0] == "123" and sent[0][1]["to"] == contacts.phone("S001") and sent[0][1]["template"]["name"] == "matches_ready"
    contacts.set_opt_in("S001", False, "test")
    assert whatsapp.send_template("S001", "matches", ["1", "x", "y"], "p") is None              # no consent, no message


def test_broadcast_plans_by_consent_and_fit(make_client):
    admin, staff = make_client("admin1"), make_client("staff1")
    contacts.set_opt_in("S002", True, "test")
    oid = admin.post("/api/listings", json={**GOOD, "title": "Broadcast Analyst"}).json()["opp_id"]
    body = {"kind": "opportunity", "opp_id": oid, "min_score": 0.0}
    assert staff.post("/api/broadcasts/preview", json=body).status_code == 403                 # admins send bulk messages
    p = admin.post("/api/broadcasts/preview", json=body).json()
    assert p["total"] >= 1 and p["reachable"] <= 1 and p["total"] == p["reachable"] + p["not_agreed"] + p["no_phone"]
    assert "recipients" not in p and "Broadcast Analyst" in p["preview"] and not p["live"]
    upd = admin.post("/api/broadcasts/preview", json={"kind": "update", "text": "Call 9876543210 for the mock interview."}).json()
    assert upd["total"] == 100 and "9876543210" not in upd["preview"]                          # phones are taken out
    assert admin.post("/api/broadcasts/preview", json={"kind": "update", "text": ""}).status_code == 422
    sent = admin.post("/api/broadcasts", json={"kind": "update", "text": "Mock interviews on Saturday.", "program": None})
    assert sent.status_code == 200 and sent.json()["queued"] >= 1 and not sent.json()["live"]
    batch = outbox.list_items(batch_id=sent.json()["batch_id"])
    assert batch and all(m["status"] == "dry_run" and m["recipient"].startswith("student:") and "*" in m["address"] for m in batch)
    contacts.set_opt_in("S002", False, "test")


def test_broadcast_plan_unit(students_small, opps_small):
    with pytest.raises(ValueError):
        broadcast.plan("spam", {})
    with pytest.raises(ValueError):
        broadcast.plan("opportunity", {})


def test_consent_by_staff_and_student(make_client):
    staff, stud, acme = make_client("staff1"), make_client("stud1"), make_client("acme")
    assert staff.put("/api/students/S001/consent", json={"whatsapp": True}).json()["whatsapp"] is True
    me = stud.get("/api/me/consent").json()
    assert me["whatsapp"] is True and me["recorded_by"] == "staff:staff1" and "phone" not in json.dumps(me)
    assert stud.put("/api/me/consent", json={"whatsapp": False}).json()["whatsapp"] is False
    assert acme.get("/api/students/S001/consent").status_code == 403


def test_webhook_student_reply_lead_and_signature(make_client, monkeypatch):
    admin, staff, c = make_client("admin1"), make_client("staff1"), make_client()
    monkeypatch.setenv("WHATSAPP_VERIFY_TOKEN", "verify-me")
    assert c.get("/api/whatsapp/webhook?hub.mode=subscribe&hub.verify_token=verify-me&hub.challenge=42").text == "42"
    assert c.get("/api/whatsapp/webhook?hub.mode=subscribe&hub.verify_token=wrong&hub.challenge=42").status_code == 403
    student_phone = contacts.phone("S003")

    def call(msgs, secret=None, sig=None):
        raw = json.dumps({"entry": [{"changes": [{"value": {"messages": msgs, "contacts": [{"wa_id": "919000000007", "profile": {"name": "Neem Robotics"}}]}}]}]}).encode()
        h = {"Content-Type": "application/json"}
        if secret:
            h["X-Hub-Signature-256"] = sig or "sha256=" + hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
        return c.post("/api/whatsapp/webhook", content=raw, headers=h)

    assert call([{"from": student_phone, "id": "wamid.s1", "type": "text", "text": {"body": "Yes I can come on Monday"}}]).status_code == 200
    thread = staff.get("/api/threads/student/S003/messages").json()
    assert thread[-1]["body"] == "Yes I can come on Monday" and thread[-1]["sender_role"] == "student"
    lead_msg = {"from": "919000000007", "id": "wamid.l1", "type": "text", "text": {"body": "We need 2 embedded systems trainees in Warangal"}}
    assert call([lead_msg]).status_code == 200
    assert call([lead_msg]).status_code == 200                                                   # Meta retries: stored once
    monkeypatch.setenv("WHATSAPP_APP_SECRET", "app-secret")
    assert call([{**lead_msg, "id": "wamid.l2"}]).status_code == 403                             # unsigned once a secret is set
    assert call([{**lead_msg, "id": "wamid.l2"}], "app-secret", "sha256=bad").status_code == 403
    assert call([{**lead_msg, "id": "wamid.l2", "text": {"body": "Pay 3 LPA"}}], "app-secret").status_code == 200

    found = [t for t in admin.get("/api/leads").json() if t["phone"] == "919000000007"]
    assert len(found) == 1 and found[0]["profile_name"] == "Neem Robotics" and found[0]["count"] == 3     # two from them, one automatic reply
    assert staff.get("/api/leads").status_code == 403
    lead = admin.get(f"/api/leads/{found[0]['id']}").json()
    assert [m["body"] for m in lead["messages"]][0].startswith("We need 2 embedded")
    sug = admin.get(f"/api/leads/{found[0]['id']}/suggest").json()
    assert (sug["city"], sug["openings"], sug["pay_text"], sug["title"]) == ("Warangal", 2, "3 lpa", "Embedded Systems Trainees")
    reply = admin.post(f"/api/leads/{found[0]['id']}/reply", json={"text": "Thanks, we will post it today."}).json()
    assert reply["thread"]["messages"][-1]["direction"] == "out"
    assert next(m for m in outbox.list_items() if m["id"] == reply["outbox_id"])["status"] == "dry_run"
    made = admin.post("/api/listings", json={**GOOD, "title": "Embedded Trainee", "lead_id": found[0]["id"]}).json()
    assert leads.get_thread(found[0]["id"])["status"] == "mapped" and leads.get_thread(found[0]["id"])["mapped_opp_id"] == made["opp_id"]


def test_webhook_refuses_unsigned_calls_in_production(make_client, monkeypatch):
    monkeypatch.setenv("COOKIE_SECURE", "1")
    assert make_client().post("/api/whatsapp/webhook", json={"entry": []}).status_code == 403


def test_outbox_and_integrations_are_for_admins(make_client):
    admin, staff = make_client("admin1"), make_client("staff1")
    assert staff.get("/api/outbox").status_code == 403 and staff.get("/api/integrations").status_code == 403
    st = admin.get("/api/integrations").json()
    assert st["email"]["live"] is False and st["whatsapp"]["live"] is False and st["google"]["connected"] is False
    assert "token" not in json.dumps(st).replace("verify_token", "")
    assert isinstance(admin.get("/api/outbox?channel=whatsapp").json(), list)
    assert admin.get("/api/outbox?channel=fax").status_code == 422


def test_test_mode_only_messages_listed_numbers(pipeline_dir, monkeypatch):
    """With real WhatsApp keys, WHATSAPP_ONLY_TO keeps synthetic students' numbers (which may be real people) safe."""
    sent = []
    monkeypatch.setenv("WHATSAPP_TOKEN", "t")
    monkeypatch.setenv("WHATSAPP_PHONE_NUMBER_ID", "123")
    monkeypatch.setattr(whatsapp, "_post", lambda cfg, payload: sent.append(payload["to"]) or "wamid.ok")
    contacts.set_opt_in("S001", True, "test")
    contacts.set_opt_in("S002", True, "test")
    monkeypatch.setenv("WHATSAPP_ONLY_TO", "+91 " + contacts.phone("S001")[2:])
    a = whatsapp.send_template("S001", "matches", ["1", "x", "y"], "p")
    b = whatsapp.send_template("S002", "matches", ["1", "x", "y"], "p")
    rows = {m["id"]: m for m in outbox.list_items()}
    assert sent == [contacts.phone("S001")] and rows[a]["status"] == "sent"
    assert rows[b]["status"] == "dry_run" and "WHATSAPP_ONLY_TO" in rows[b]["error"]
    lead = whatsapp.send_text("919000000099", "hello", kind="lead_reply", recipient="lead:9")
    assert next(m for m in outbox.list_items() if m["id"] == lead)["status"] == "dry_run"
    contacts.set_opt_in("S001", False, "test")
    contacts.set_opt_in("S002", False, "test")


def _lead_message(client, phone, text, wamid):
    return client.post("/api/whatsapp/webhook", json={"entry": [{"changes": [{"value": {
        "contacts": [{"wa_id": phone, "profile": {"name": "Hiring Manager"}}],
        "messages": [{"from": phone, "id": wamid, "type": "text", "text": {"body": text}}]}}]}]})


def test_first_message_from_an_employer_gets_one_automatic_reply_asking_for_details(make_client):
    c, phone = make_client(), "919000000701"
    assert _lead_message(c, phone, "We are hiring testers", "wamid.auto.1").status_code == 200
    assert _lead_message(c, phone, "Pay is 4 LPA", "wamid.auto.2").status_code == 200
    assert _lead_message(c, phone, "Pay is 4 LPA", "wamid.auto.2").status_code == 200           # Meta retries the same message
    t = next(x for x in leads.list_threads() if x["phone"] == phone)
    msgs = make_client("admin1").get(f"/api/leads/{t['id']}").json()["messages"]
    assert [m["direction"] for m in msgs] == ["in", "out", "in"] and msgs[1]["body"] == leads.AUTO_REPLY and msgs[1]["sent_by"] == "automatic reply"
    assert sum(m["recipient"] == f"lead:{t['id']}" for m in outbox.list_items()) == 1


def test_a_lead_can_be_linked_to_a_listing_that_is_already_live(make_client):
    admin, phone = make_client("admin1"), "919000000702"
    _lead_message(make_client(), phone, "Do you have QA people for our opening?", "wamid.link.1")
    t = next(x for x in leads.list_threads() if x["phone"] == phone)
    assert admin.post(f"/api/leads/{t['id']}/status", json={"status": "mapped", "opp_id": "NOPE"}).status_code == 422
    r = admin.post(f"/api/leads/{t['id']}/status", json={"status": "mapped", "opp_id": "J001"}).json()
    assert r["status"] == "mapped" and r["mapped_opp_id"] == "J001"


def test_approving_a_listing_can_tell_the_best_fits_on_whatsapp_by_itself(make_client):
    admin, acme = make_client("admin1"), make_client("acme")
    for sid in ("S001", "S002"):
        contacts.set_opt_in(sid, True, "test")
    make = lambda title: acme.post("/api/me/listings?submit=true", json={**GOOD, "title": title, "mode": "remote", "city": ""}).json()["opp_id"]  # noqa: E731
    before = len(outbox.list_items(channel="whatsapp", limit=1000))
    r = admin.post(f"/api/listings/{make('Quiet Analyst')}/review", json={"decision": "approve", "safety_score": 4, "note": ""}).json()
    assert r["told"] == 0 and len(outbox.list_items(channel="whatsapp", limit=1000)) == before   # only when the box is ticked
    r = admin.post(f"/api/listings/{make('Announced Analyst')}/review", json={"decision": "approve", "safety_score": 4, "note": "", "tell_students": True}).json()
    assert r["told"] >= 1
    sent = outbox.list_items(channel="whatsapp", limit=1000)[:r["told"]]
    assert all(m["kind"] == "opportunity" and m["recipient"].split(":")[1] in contacts.opted_in() for m in sent)
    posted = admin.post("/api/listings", json={**GOOD, "title": "Posted Analyst", "mode": "remote", "city": "", "tell_students": True}).json()
    assert posted["status"] == "active" and posted["told"] >= 1
    for sid in ("S001", "S002"):
        contacts.set_opt_in(sid, False, "test")


def test_ngo_messages_alert_by_whatsapp_and_email_once_until_read(make_client):
    from matcher import accounts
    staff, stud, acme = make_client("staff1"), make_client("pupil5"), make_client("acme")
    staff.put("/api/students/S005/consent", json={"whatsapp": True})

    def alerts():
        rows = [r for r in outbox.list_items(limit=1000) if r["recipient"] == "student:S005"]
        return [r for r in rows if r["kind"] in ("message", "update")]
    before = len(alerts())
    url = "/api/threads/student/S005/messages"
    for text in ("Your interview moved to Friday, room 4.", "Also bring your marksheet."):
        assert staff.post(url, json={"body": text}).status_code == 200
    new = alerts()[: len(alerts()) - before]
    assert sorted((r["channel"], r["kind"]) for r in new) == [("email", "message"), ("whatsapp", "update")]   # one of each
    assert all("Friday" not in r["body"] and "marksheet" not in r["body"] for r in new)                    # never the text
    assert all("/student/messages" in r["body"] for r in new)

    stud.get(url)                                                                     # reading resets it
    staff.post(url, json={"body": "One more thing."})
    assert len(alerts()) - before == 4

    stud.put("/api/me/consent", json={"whatsapp": False})
    stud.get(url)
    staff.post(url, json={"body": "After opting out."})
    newest = alerts()[0]
    assert len(alerts()) - before == 5 and newest["channel"] == "email"            # email only once they opt out
    stud.post(url, json={"body": "Thanks!"})
    assert len(alerts()) - before == 5                                               # a student's own message sends nothing

    accounts.set_email(accounts.get_by_username("acme").id, "hr@acme.example.com")
    acme.get("/api/threads/listing/J028/messages")
    staff.post("/api/threads/listing/J028/messages", json={"body": "Can you share the interview panel?"})
    mail = next(r for r in outbox.list_items(channel="email", limit=50) if r["kind"] == "message" and r["recipient"].startswith("user:"))
    assert "panel" not in mail["body"] and "/employer/messages?listing=J028" in mail["body"]
