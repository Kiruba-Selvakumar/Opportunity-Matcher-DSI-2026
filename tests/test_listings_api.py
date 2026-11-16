"""Employers post listings, the NGO reviews them, and approved ones take part in matching straight away."""
import pytest

GOOD = {"title": "Remote Data Analyst Intern", "org_name": "Acme Data", "required_skills_text": "Excel, SQL, Power BI is a plus",
        "mode": "remote", "pay_text": "3.6 LPA", "hours_per_week": 40, "openings": 1, "description": "Work on dashboards."}


def post(c, body=None, submit=True):
    r = c.post(f"/api/me/listings?submit={'true' if submit else 'false'}", json={**GOOD, **(body or {})})
    assert r.status_code == 200, r.text
    return r.json()


def approve(staff, oid, score=4, note="Fine"):
    r = staff.post(f"/api/listings/{oid}/review", json={"decision": "approve", "safety_score": score, "note": note})
    assert r.status_code == 200, r.text
    return r.json()


def in_matching(staff, oid):
    return staff.get(f"/api/opportunities/{oid}").status_code == 200


def test_post_review_approve_and_it_is_matched_straight_away(make_client):
    acme, staff = make_client("acme"), make_client("admin1")
    made = post(acme)
    oid = made["opp_id"]
    assert made["status"] == "pending" and oid.startswith("E")
    assert not in_matching(staff, oid)                                    # waiting for review: nobody is matched to it
    queue = staff.get("/api/listings/review").json()
    item = next(i for i in queue if i["opp_id"] == oid)
    assert item["owner"] == "Acme" and item["mapped_skills"] >= 2 and item["flags"] == []
    done = approve(staff, oid, 4)
    assert done["status"] == "active" and done["safety_score"] == 4
    assert in_matching(staff, oid)                                        # live, with no restart
    d = staff.get(f"/api/opportunities/{oid}").json()
    assert d["candidates"] and d["safety_score"] == 4
    mine = {x["opp_id"]: x for x in acme.get("/api/me/listings").json()}
    assert mine[oid]["status"] == "active" and mine[oid]["eligible_count"] > 0 and mine["J028"]["editable"] is False


def test_a_draft_is_invisible_and_can_be_submitted_later(make_client):
    acme, staff = make_client("acme"), make_client("staff1")
    oid = post(acme, submit=False)["opp_id"]
    assert all(i["opp_id"] != oid for i in staff.get("/api/listings/review?status=all").json())
    assert not in_matching(staff, oid)
    assert acme.post(f"/api/me/listings/{oid}/submit").json()["status"] == "pending"
    assert acme.post(f"/api/me/listings/{oid}/submit").status_code == 422   # already submitted


def test_editing_a_live_listing_takes_it_out_of_matching_until_reviewed_again(make_client):
    acme, staff = make_client("acme"), make_client("admin1")
    oid = post(acme)["opp_id"]; approve(staff, oid)
    assert in_matching(staff, oid)
    r = acme.put(f"/api/me/listings/{oid}?submit=true", json={**GOOD, "title": "Senior Data Analyst Intern"})
    assert r.json()["status"] == "pending" and r.json()["edited_since_review"] is True
    assert not in_matching(staff, oid)
    approve(staff, oid)
    assert staff.get(f"/api/opportunities/{oid}").json()["title"] == "Senior Data Analyst Intern"


def test_reject_needs_a_reason_and_the_employer_sees_it(make_client):
    acme, staff = make_client("acme"), make_client("admin1")
    oid = post(acme)["opp_id"]
    bad = staff.post(f"/api/listings/{oid}/review", json={"decision": "reject", "safety_score": 2, "note": ""})
    assert bad.status_code == 422 and "why" in bad.json()["detail"]
    assert staff.post(f"/api/listings/{oid}/review", json={"decision": "reject", "safety_score": 2, "note": "Pay is unclear."}).status_code == 200
    seen = acme.get(f"/api/me/listings/{oid}").json()
    assert seen["status"] == "rejected" and seen["review_note"] == "Pay is unclear." and seen["form"]["title"] == GOOD["title"]
    assert not in_matching(staff, oid)
    assert acme.put(f"/api/me/listings/{oid}?submit=true", json=GOOD).json()["status"] == "pending"   # fix and resubmit


def test_close_reopen_and_copy(make_client):
    acme, staff = make_client("acme"), make_client("admin1")
    oid = post(acme)["opp_id"]; approve(staff, oid)
    assert acme.post(f"/api/me/listings/{oid}/close").json()["status"] == "closed" and not in_matching(staff, oid)
    assert acme.post(f"/api/me/listings/{oid}/close").status_code == 422
    assert acme.post(f"/api/me/listings/{oid}/reopen").json()["status"] == "active" and in_matching(staff, oid)
    cp = acme.post(f"/api/me/listings/{oid}/copy").json()
    assert cp["status"] == "draft" and cp["form"]["title"].endswith("(copy)") and cp["opp_id"] != oid
    assert staff.post(f"/api/listings/{oid}/close").json()["status"] == "closed"                      # the NGO can close it too
    assert not in_matching(staff, oid)


def test_red_flags_reach_the_reviewer(make_client):
    acme, staff = make_client("acme"), make_client("staff1")
    oid = post(acme, {"upfront_cost_text": "Rs 5,000", "description": "WhatsApp us on 9876543210", "night_shift": True,
                      "hours_per_week": 60, "pay_text": ""})["opp_id"]
    flags = next(i for i in staff.get("/api/listings/review").json() if i["opp_id"] == oid)["flags"]
    assert [f["level"] for f in flags].count("red") == 2 and len(flags) >= 5
    assert "9876543210" not in str(acme.get(f"/api/me/listings/{oid}").json())      # contact details are removed from the text


def test_validation_and_unknown_fields(make_client):
    acme = make_client("acme")
    for bad in ({"title": "ab"}, {"hours_per_week": 99}, {"openings": 0}, {"mode": "onsite", "city": ""}, {"type": "mentor"},
                {"languages": []}, {"required_skills_text": "x"}):
        assert acme.post("/api/me/listings?submit=false", json={**GOOD, **bad}).status_code == 422, bad
    assert acme.post("/api/me/listings?submit=false", json={**GOOD, "status": "active"}).status_code == 422   # cannot pick a status


def test_nobody_else_can_touch_a_listing(make_client):
    acme, other, staff, stud = make_client("acme"), make_client("other"), make_client("staff1"), make_client("stud1")
    oid = post(acme)["opp_id"]
    for call in (lambda c: c.get(f"/api/me/listings/{oid}"), lambda c: c.put(f"/api/me/listings/{oid}", json=GOOD),
                 lambda c: c.post(f"/api/me/listings/{oid}/close"), lambda c: c.post(f"/api/me/listings/{oid}/copy")):
        assert call(other).status_code == 404
    assert acme.put("/api/me/listings/J028", json=GOOD).status_code == 404                          # sample listings are the NGO's
    assert acme.post("/api/me/listings/J028/close").status_code == 404
    for c in (staff, stud):
        assert c.post("/api/me/listings?submit=true", json=GOOD).status_code == 403
        assert c.get("/api/me/listings").status_code == 403
    for c in (acme, stud):
        assert c.get("/api/listings/review").status_code == 403
        assert c.post(f"/api/listings/{oid}/review", json={"decision": "approve", "safety_score": 3}).status_code == 403
    assert make_client("other").get("/api/me/listings").json() != acme.get("/api/me/listings").json()


def test_the_audit_log_and_notifications_follow_the_flow(make_client):
    acme, staff, admin = make_client("acme"), make_client("staff1"), make_client("admin1")
    before, staff_before = admin.get("/api/notifications").json()["unread"], staff.get("/api/notifications").json()["unread"]
    oid = post(acme)["opp_id"]
    assert admin.get("/api/notifications").json()["unread"] == before + 1           # reviews are the admin's queue
    assert staff.get("/api/notifications").json()["unread"] == staff_before
    approve(admin, oid)
    mine = acme.get("/api/notifications").json()["items"]
    assert any("approved" in n["text"] and n["link"] == f"/employer/{oid}" for n in mine)
    actions = [e["action"] for e in admin.get(f"/api/admin/audit?limit=300").json() if e["target"] == oid]
    assert {"listing.created", "listing.reviewed"} <= set(actions)


def test_employers_can_message_about_a_listing_that_is_not_live_yet(make_client):
    acme, staff = make_client("acme"), make_client("staff1")
    oid = post(acme)["opp_id"]                                              # pending, so not in matching
    assert acme.post(f"/api/threads/listing/{oid}/messages", json={"body": "Can you review this today?"}).status_code == 200
    assert any(m["body"].startswith("Can you review") for m in staff.get(f"/api/threads/listing/{oid}/messages").json())
    assert make_client("other").get(f"/api/threads/listing/{oid}/messages").status_code == 404


def test_only_an_admin_reviews_posts_or_closes(make_client):
    acme, staff, admin = make_client("acme"), make_client("staff1"), make_client("admin1")
    oid = post(acme)["opp_id"]
    assert staff.get("/api/listings/review").status_code == 200                       # staff can see the queue
    assert staff.post(f"/api/listings/{oid}/review", json={"decision": "approve", "safety_score": 3}).status_code == 403
    assert staff.post("/api/listings", json=GOOD).status_code == 403
    approve(admin, oid)
    assert staff.post(f"/api/listings/{oid}/close").status_code == 403
    assert acme.post("/api/me/listings", json={**GOOD, "type": "mentor"}).status_code == 422   # mentors come from the NGO


def test_approval_emails_the_employer(make_client, monkeypatch):
    from matcher import accounts, outbox
    monkeypatch.setenv("OUTBOX_SYNC", "1")
    acme, admin = make_client("acme"), make_client("admin1")
    accounts.set_email(accounts.get_by_username("acme").id, "hr@acme.example.com")
    oid = post(acme)["opp_id"]
    assert approve(admin, oid)["emailed"] == 1
    mail = next(m for m in outbox.list_items(channel="email") if m["kind"] == "listing_reviewed")
    assert mail["address"] == "hr@acme.example.com" and mail["status"] == "dry_run" and f"/employer/{oid}" in mail["body"]
    assert "is live" in mail["subject"]


def test_an_admin_posts_a_listing_that_is_live_at_once(make_client):
    from datetime import date, timedelta
    admin, staff = make_client("admin1"), make_client("staff1")
    soon = (date.today() + timedelta(days=5)).isoformat()
    made = admin.post("/api/listings", json={**GOOD, "title": "NGO Data Fellowship", "apply_by": soon, "owner_username": "acme"})
    assert made.status_code == 200, made.text
    oid = made.json()["opp_id"]
    assert made.json()["status"] == "active" and in_matching(staff, oid)
    row = next(o for o in staff.get("/api/opportunities").json() if o["opp_id"] == oid)
    assert row["apply_by"] == soon and row["closing_soon"]
    assert oid in [x["opp_id"] for x in make_client("acme").get("/api/me/listings").json()]   # the employer can manage it too
    edited = admin.put(f"/api/listings/{oid}", json={**GOOD, "title": "NGO Data Fellowship 2026"})
    assert edited.json()["status"] == "active" and staff.get(f"/api/opportunities/{oid}").json()["title"] == "NGO Data Fellowship 2026"
    assert admin.post("/api/listings", json={**GOOD, "owner_username": "staff1"}).status_code == 422
    mentor = admin.post("/api/listings", json={**GOOD, "type": "mentor", "title": "Alumni mentor: SQL"})
    assert mentor.status_code == 200 and mentor.json()["form"]["type"] == "mentor"


def test_a_listing_closes_when_its_last_day_passes(make_client, monkeypatch):
    from datetime import date, timedelta

    from api import deps
    from matcher import listings
    admin, staff = make_client("admin1"), make_client("staff1")
    oid = admin.post("/api/listings", json={**GOOD, "apply_by": (date.today() + timedelta(days=1)).isoformat()}).json()["opp_id"]
    assert in_matching(staff, oid)
    real = listings.close_expired
    monkeypatch.setattr(listings, "close_expired", lambda: real(today=date.today() + timedelta(days=2)))
    assert oid in deps.sweep(deps.state(), force=True)
    assert not in_matching(staff, oid)


def test_a_new_company_can_send_its_first_proposal_and_the_admin_approves_it(make_client):
    from matcher import accounts

    from .conftest import PASSWORD
    accounts.create_user("newco", "New Company", "employer", password=PASSWORD, must_change=False)
    newco = make_client("newco")
    assert newco.get("/api/me/listings").json() == []
    oid = newco.post("/api/me/listings?submit=true", json={**GOOD, "title": "First Proposal Analyst"}).json()["opp_id"]
    assert [x["opp_id"] for x in newco.get("/api/me/listings").json()] == [oid]
    r = make_client("admin1").post(f"/api/listings/{oid}/review", json={"decision": "approve", "safety_score": 4, "note": ""})
    assert r.status_code == 200 and r.json()["status"] == "active"


def test_a_listing_from_the_data_file_leaves_matching_after_its_last_day_and_nothing_breaks(make_client):
    from api import deps
    stud, admin = make_client("pupil4"), make_client("admin1")
    st = deps.state()
    oid = next(r.opp_id for r in st.rows_by_student["S004"] if r.eligible and r.type == "job")
    app = stud.post("/api/me/applications", json={"opp_id": oid}).json()
    assert app["opp_id"] == oid
    past = st.pipeline_opps[oid].model_copy(update={"apply_by": "2020-01-01"})
    st.pipeline_opps[oid] = past
    st.opps = {**st.opps, oid: past}
    assert deps.sweep(st, force=True) == [oid]
    assert oid not in st.opps and all(r.opp_id != oid for r in st.rows_by_student["S004"])
    assert stud.post("/api/me/applications", json={"opp_id": oid}).status_code == 404
    mine = stud.get("/api/me/applications").json()
    assert next(a for a in mine if a["opp_id"] == oid)["title"] == past.title                     # it keeps its name in their list
    assert any("last day" in n["text"] for n in stud.get("/api/notifications").json()["items"])
    for path in (f"/api/applications/{app['id']}/review", "/api/applications", "/api/dashboard", "/api/opportunities"):
        assert admin.get(path).status_code == 200, path
    deps.reset_state()


def test_an_admin_edit_keeps_the_new_safety_score(make_client):
    admin, staff = make_client("admin1"), make_client("staff1")
    made = admin.post("/api/listings", json={**GOOD, "title": "NGO Safety Check", "safety_score": 4}).json()
    oid = made["opp_id"]
    assert made["safety_score"] == 4
    r = admin.put(f"/api/listings/{oid}", json={**GOOD, "title": "NGO Safety Check", "safety_score": 2})
    assert r.status_code == 200 and r.json()["safety_score"] == 2
    assert admin.get(f"/api/listings/{oid}/form").json()["safety_score"] == 2
    assert staff.get(f"/api/opportunities/{oid}").json()["safety_score"] == 2                 # matching uses the new score
    admin.put(f"/api/listings/{oid}", json={**GOOD, "title": "NGO Safety Check, renamed"})     # no score sent: it stays
    assert admin.get(f"/api/listings/{oid}/form").json()["safety_score"] == 2
