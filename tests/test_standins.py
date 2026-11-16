"""Test stand-ins. Meta, SMTP and Google are fakes that record where each message was really going: nothing leaves."""
import smtplib

import pytest

from matcher import accounts, contacts, config, generate_students, google_calendar, leads, mailer, meetings, outbox, pipeline, settings, standins, whatsapp

ME, FRIEND, EMPLOYER_PHONE = "919000000001", "919000000002", "919000000003"


@pytest.fixture(autouse=True)
def sync(monkeypatch):
    monkeypatch.setenv("OUTBOX_SYNC", "1")
    monkeypatch.delenv("WHATSAPP_ONLY_TO", raising=False)
    monkeypatch.delenv("STANDIN_WHATSAPP", raising=False)
    monkeypatch.delenv("STANDIN_EMAIL", raising=False)


@pytest.fixture
def meta(monkeypatch):
    """Live WhatsApp keys with Meta faked. Returns the numbers messages were sent to."""
    sent = []
    monkeypatch.setenv("WHATSAPP_TOKEN", "t")
    monkeypatch.setenv("WHATSAPP_PHONE_NUMBER_ID", "123")
    monkeypatch.setattr(whatsapp, "_post", lambda cfg, payload: sent.append(payload["to"]) or f"wamid.{len(sent)}")
    monkeypatch.setattr(contacts, "opted_in", lambda path=None: {"S001", "S002", "S003"})
    return sent


@pytest.fixture
def smtp(monkeypatch):
    """Live SMTP with the connection faked, so the real message is built. Returns every message handed to the server."""
    sent = []

    class Fake:
        def __init__(self, *a, **kw): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def starttls(self, **kw): pass
        def login(self, *a): pass
        def send_message(self, msg): sent.append(msg)

    monkeypatch.setenv("SMTP_HOST", "smtp.example.org")
    monkeypatch.setenv("SMTP_USER", "ngo@example.org")
    monkeypatch.setattr(smtplib, "SMTP", Fake)
    return sent


def row(oid):
    return next(m for m in outbox.list_items() if m["id"] == oid)


# ---- switched off: production behaviour ----

def test_with_no_settings_messages_go_to_the_real_addresses(pipeline_dir, meta, smtp):
    assert not standins.active()
    whatsapp.send_template("S001", "matches", ["3", "QA", "x"], "preview")
    mailer.send("hr@acme.example.com", "Hello", "body", kind="t", recipient="user:1")
    assert meta == [contacts.phone("S001")]
    assert smtp[0]["To"] == "hr@acme.example.com" and smtp[0]["Subject"] == "Hello"
    assert standins.calendar_guests(["hr@acme.example.com"]) == ["hr@acme.example.com"]
    assert standins.incoming_student(contacts.phone("S001")) == "S001"


# ---- WhatsApp ----

def test_a_student_with_a_stand_in_gets_it_there_and_the_fake_number_is_never_used(pipeline_dir, meta, monkeypatch):
    monkeypatch.setenv("STANDIN_WHATSAPP", f"S001={ME}")
    oid = whatsapp.send_template("S001", "matches", ["3", "QA", "x"], "preview")
    assert meta == [ME] and contacts.phone("S001") not in meta
    m = row(oid)
    assert m["status"] == "sent" and m["recipient"] == "student:S001"
    assert m["address"] == f"{outbox.mask(contacts.phone('S001'))} via {outbox.mask(ME)}"


def test_a_student_without_a_stand_in_is_held_even_with_live_keys(pipeline_dir, meta, monkeypatch):
    monkeypatch.setenv("STANDIN_WHATSAPP", f"S001={ME}")
    m = row(whatsapp.send_template("S002", "matches", ["3", "QA", "x"], "preview"))
    assert meta == [] and m["status"] == "dry_run" and m["error"] == standins.HELD


def test_setting_only_email_stand_ins_still_holds_all_whatsapp(pipeline_dir, meta, monkeypatch):
    monkeypatch.setenv("STANDIN_EMAIL", "*=me@gmail.test")
    m = row(whatsapp.send_template("S001", "matches", ["3", "QA", "x"], "preview"))
    assert meta == [] and m["status"] == "dry_run"


def test_consent_still_decides_who_gets_a_message(pipeline_dir, meta, monkeypatch):
    monkeypatch.setenv("STANDIN_WHATSAPP", f"S009={ME}")
    assert whatsapp.send_template("S009", "matches", ["3", "QA", "x"], "preview") is None and meta == []


def test_two_students_can_share_one_phone_going_out(pipeline_dir, meta, monkeypatch):
    monkeypatch.setenv("STANDIN_WHATSAPP", f"S001={ME},S002={ME}")
    whatsapp.send_template("S001", "matches", ["3", "QA", "x"], "preview")
    whatsapp.send_template("S002", "matches", ["3", "QA", "x"], "preview")
    assert meta == [ME, ME]


def test_ten_digit_numbers_are_accepted(monkeypatch):
    monkeypatch.setenv("STANDIN_WHATSAPP", "S001=90000 00001")
    assert standins.whatsapp_for_student("S001") == ME


# ---- one phone for every student, the usual way to test ----

def test_star_sends_every_student_to_one_phone_and_a_name_overrides_it(pipeline_dir, meta, monkeypatch):
    monkeypatch.setenv("STANDIN_WHATSAPP", f"*={FRIEND},S003={ME}")
    for sid in ("S001", "S002", "S003"):
        whatsapp.send_template(sid, "matches", ["3", "QA", "x"], "preview")
    assert meta == [FRIEND, FRIEND, ME]


def test_a_reply_from_the_shared_phone_lands_with_the_student_it_last_heard_about(make_client, meta, monkeypatch):
    monkeypatch.setenv("STANDIN_WHATSAPP", f"*={FRIEND}")
    whatsapp.send_template("S001", "matches", ["3", "QA", "x"], "preview")
    whatsapp.send_template("S002", "matches", ["3", "QA", "x"], "preview")
    webhook(make_client(), FRIEND, "Is this for me", "wamid.standin.star")
    assert any(m["body"] == "Is this for me" for m in make_client("admin1").get("/api/threads/student/S002/messages").json())
    assert not any(t["phone"] == FRIEND for t in leads.list_threads())


def test_a_phone_under_a_staff_name_plays_an_employer(make_client, meta, monkeypatch):
    me = "919000000004"
    monkeypatch.setenv("STANDIN_WHATSAPP", f"*={FRIEND},admin={me}")
    webhook(make_client(), me, "We are hiring 2 testers", "wamid.standin.admin")
    lead = next(t for t in leads.list_threads() if t["phone"] == me)
    make_client("admin1").post(f"/api/leads/{lead['id']}/reply", json={"text": "Thanks"})
    assert meta == [me, me]                                                                    # the automatic first reply, then the admin's


def test_nothing_stops_people_sharing_a_real_address(make_client):
    """There is no uniqueness rule on emails or on the contact list, so accounts can share one."""
    for username in ("admin1", "staff1", "acme"):
        accounts.set_email(accounts.get_by_username(username).id, "shared@gmail.test")
    assert accounts.get_by_username("admin1").email == accounts.get_by_username("acme").email == "shared@gmail.test"
    for username, address in (("admin1", None), ("staff1", None), ("acme", "hr@acme.example.com")):
        accounts.set_email(accounts.get_by_username(username).id, address)


# ---- email ----

def test_email_goes_to_the_stand_in_named_by_username(make_client, smtp, monkeypatch):
    accounts.set_email(accounts.get_by_username("acme").id, "hr@acme.example.com")
    monkeypatch.setenv("STANDIN_EMAIL", "acme=me+employer@gmail.test")
    oid = mailer.send("hr@acme.example.com", "Your listing is live", "body", kind="t", recipient="user:1")
    assert smtp[0]["To"] == "me+employer@gmail.test" and smtp[0]["Subject"] == "[TEST for acme] Your listing is live"
    assert "via m***@gmail.test" in row(oid)["address"]


def test_email_without_a_stand_in_or_catch_all_is_held(make_client, smtp, monkeypatch):
    monkeypatch.setenv("STANDIN_EMAIL", "acme=me@gmail.test")
    m = row(mailer.send("stranger@real-company.test", "Hi", "body", kind="t", recipient="interviewer:x"))
    assert smtp == [] and m["status"] == "dry_run" and m["error"] == standins.HELD


def test_catch_all_takes_everyone_else_and_says_who_it_was_for(make_client, smtp, monkeypatch):
    monkeypatch.setenv("STANDIN_EMAIL", "*=me@gmail.test")
    mailer.send("stranger@real-company.test", "Hi", "body", kind="t", recipient="interviewer:x")
    assert smtp[0]["To"] == "me@gmail.test" and "stranger@real-company.test" in smtp[0]["Subject"]


def test_a_student_email_is_stored_masked_and_routed_by_id(pipeline_dir, smtp, monkeypatch):
    monkeypatch.setenv("STANDIN_EMAIL", f"S001=me@gmail.test")
    real = contacts.email("S001")
    oid = mailer.send(real, "Interview", "body", kind="interview", recipient="student:S001")
    assert smtp[0]["To"] == "me@gmail.test" and smtp[0]["Subject"].startswith("[TEST for S001]")
    assert real not in row(oid)["address"] and outbox.mask(real) in row(oid)["address"]


def test_employer_and_student_on_one_inbox_both_get_their_invite(make_client, smtp, monkeypatch):
    """Reusing one address in the data would lose an invite, because invites are de-duplicated by address. Stand-ins do not."""
    accounts.set_email(accounts.get_by_username("acme").id, "hr@acme.example.com")
    monkeypatch.setenv("STANDIN_EMAIL", "*=me@gmail.test")
    iv = {"id": 7, "starts_at": "2030-01-01T10:00:00+05:30", "minutes": 30, "mode": "meet", "meet_link": "https://meet.test/x", "location": None,
          "sequence": 0, "interviewer_email": None, "student_invited": 1, "student_id": "S001", "candidate_code": "abc"}
    assert meetings._send_ics(iv, "QA", ["hr@acme.example.com"]) == 2
    assert [m["To"] for m in smtp] == ["me@gmail.test", "me@gmail.test"]
    assert "acme" in smtp[0]["Subject"] and "S001" in smtp[1]["Subject"]


# ---- Google Calendar ----

def test_google_guest_list_holds_only_stand_ins_and_the_notetaker(make_client, monkeypatch):
    calls = []
    monkeypatch.setenv("FIREFLIES_API_KEY", "k")
    monkeypatch.setenv("STANDIN_EMAIL", "S001=me@gmail.test")
    monkeypatch.setattr(google_calendar, "_call", lambda method, url, **kw: calls.append(kw["json"]) or {"id": "e1", "hangoutLink": "https://meet.test/y"})
    from datetime import datetime
    google_calendar.create_event("Interview", "d", datetime(2030, 1, 1, 10), 30, [contacts.email("S001"), "hr@acme.example.com", "fred@fireflies.ai"])
    assert [g["email"] for g in calls[0]["attendees"]] == ["me@gmail.test", "fred@fireflies.ai"]


# ---- coming back in ----

def webhook(client, frm, text, wamid):
    body = {"entry": [{"changes": [{"value": {"contacts": [{"wa_id": frm, "profile": {"name": "Tester"}}],
                                              "messages": [{"from": frm, "id": wamid, "type": "text", "text": {"body": text}}]}}]}]}
    assert client.post("/api/whatsapp/webhook", json=body).status_code == 200


def test_a_reply_from_a_stand_in_lands_in_that_students_chat(make_client, monkeypatch):
    monkeypatch.setenv("STANDIN_WHATSAPP", f"S003={ME}")
    webhook(make_client(), ME, "Yes I can attend", "wamid.standin.1")
    msgs = make_client("admin1").get("/api/threads/student/S003/messages").json()
    assert any(m["body"] == "Yes I can attend" for m in msgs)
    assert not any(t["phone"] == ME for t in leads.list_threads())


def test_a_phone_marked_lead_plays_an_employer_and_can_be_replied_to(make_client, monkeypatch, meta):
    monkeypatch.setenv("STANDIN_WHATSAPP", f"S003={ME},lead={EMPLOYER_PHONE}")
    webhook(make_client(), EMPLOYER_PHONE, "Hiring 2 testers in Hyderabad", "wamid.standin.2")
    lead = next(t for t in leads.list_threads() if t["phone"] == EMPLOYER_PHONE)
    r = make_client("admin1").post(f"/api/leads/{lead['id']}/reply", json={"text": "Thanks, we will call you."})
    assert r.status_code == 200 and meta == [EMPLOYER_PHONE, EMPLOYER_PHONE]                   # the automatic first reply, then the admin's


def test_a_reply_to_a_number_not_on_the_list_is_held(make_client, monkeypatch, meta):
    monkeypatch.setenv("STANDIN_WHATSAPP", f"S003={ME}")
    stranger = "919000000099"
    webhook(make_client(), stranger, "Who is this?", "wamid.standin.3")
    lead = next(t for t in leads.list_threads() if t["phone"] == stranger)
    r = make_client("admin1").post(f"/api/leads/{lead['id']}/reply", json={"text": "Hello"})
    assert meta == [] and row(r.json()["outbox_id"])["error"] == standins.HELD


# ---- what people see, and what stops the app ----

def test_settings_and_broadcast_preview_show_test_mode(make_client, monkeypatch):
    admin = make_client("admin1")
    assert admin.get("/api/integrations").json()["test_mode"]["active"] is False
    monkeypatch.setenv("STANDIN_WHATSAPP", f"S001={ME}")
    monkeypatch.setattr(contacts, "opted_in", lambda path=None: {"S001", "S002"})
    assert admin.get("/api/integrations").json()["test_mode"]["active"] is True
    p = admin.post("/api/broadcasts/preview", json={"kind": "update", "text": "Mock interview day on Friday"}).json()
    assert p["reachable"] == 2 and p["stand_ins"] == 1
    monkeypatch.setenv("STANDIN_WHATSAPP", f"*={FRIEND}")
    assert admin.post("/api/broadcasts/preview", json={"kind": "update", "text": "Mock interview day on Friday"}).json()["stand_ins"] == 2


@pytest.mark.parametrize("name,value", [("STANDIN_WHATSAPP", "S001"), ("STANDIN_WHATSAPP", "S001=abc"), ("STANDIN_EMAIL", "S001=not-an-email"), ("STANDIN_EMAIL", "=x@y.test")])
def test_a_typo_in_the_settings_stops_the_app(pipeline_dir, monkeypatch, name, value):
    monkeypatch.setenv(name, value)
    assert any(name in p for p in settings.check_production_ready())


def test_live_whatsapp_on_the_sample_students_stops_the_app(pipeline_dir, monkeypatch):
    monkeypatch.setenv("WHATSAPP_TOKEN", "t")
    monkeypatch.setenv("WHATSAPP_PHONE_NUMBER_ID", "123")
    assert any("sample students" in p for p in settings.check_production_ready())
    monkeypatch.setenv("STANDIN_WHATSAPP", f"S001={ME}")
    assert settings.check_production_ready() == []


def test_live_whatsapp_on_real_contacts_is_allowed(pipeline_dir, monkeypatch, tmp_path):
    real = tmp_path / "contacts.csv"
    real.write_text("student_id,name,phone,email\nS001,A Student,9000000001,a.student@college.test\n")
    monkeypatch.setitem(config.PATHS, "contacts", real)
    monkeypatch.setenv("WHATSAPP_TOKEN", "t")
    monkeypatch.setenv("WHATSAPP_PHONE_NUMBER_ID", "123")
    assert settings.check_production_ready() == []


# ---- real data is safe from the sample generator ----

def test_the_pipeline_never_overwrites_real_students(pipeline_dir, monkeypatch, tmp_path):
    students, opps = tmp_path / "students.csv", tmp_path / "opps.csv"
    real = "student_id,name,phone,email\nS001,A Student,9000000001,a.student@college.test\n"
    students.write_text(real)
    opps.write_text("opp_id\nJ1\n")
    monkeypatch.setitem(config.PATHS, "students_raw", students)
    monkeypatch.setitem(config.PATHS, "opportunities_raw", opps)
    assert "kept" in pipeline._data()
    generate_students.main()
    assert students.read_text() == real and opps.read_text() == "opp_id\nJ1\n"


def test_blank_emails_count_as_real_data(tmp_path):
    f = tmp_path / "s.csv"
    f.write_text("student_id,email\nS001,\n")
    assert generate_students.holds_real_data(f)
    f.write_text("student_id,email\nS001,a.b1@example.com\n")
    assert not generate_students.holds_real_data(f)
    assert not generate_students.holds_real_data(tmp_path / "missing.csv")
