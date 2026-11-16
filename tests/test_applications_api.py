"""A student shows interest, the NGO shares it, the employer moves it along. Each side sees only its own part."""
import json
import re

from api import deps

from .test_listings_api import GOOD, approve, post


def live_listing(acme, staff, **kw):
    oid = post(acme, kw or None)["opp_id"]
    approve(staff, oid)
    return oid


def status_of(client, oid):
    return next((a["status"] for a in client.get("/api/me/applications").json() if a["opp_id"] == oid), None)


def test_the_whole_journey_and_who_sees_what(make_client):
    acme, staff, admin, stud = make_client("acme"), make_client("staff1"), make_client("admin1"), make_client("pupil4")
    oid = live_listing(acme, admin, openings=1)

    app = stud.post("/api/me/applications", json={"opp_id": oid, "note": "I know Excel well. Call me 9876543210"}).json()
    assert app["status"] == "interested" and "9876543210" not in json.dumps(app) and app["can_withdraw"]
    assert stud.post("/api/me/applications", json={"opp_id": oid}).status_code == 422               # no duplicates
    assert acme.get(f"/api/me/listings/{oid}").json()["applicants"] == []                            # not shared yet: the employer sees nothing
    assert acme.post(f"/api/me/applications/{app['id']}/status", json={"status": "shortlisted"}).status_code == 404

    queue = staff.get(f"/api/applications?status=interested&opp_id={oid}").json()
    assert [q["student_id"] for q in queue] == ["S004"] and queue[0]["next"] == ["declined"] and queue[0]["can_recommend"]
    assert staff.post(f"/api/applications/{app['id']}/status", json={"status": "hired"}).status_code == 422   # cannot skip ahead
    assert staff.post(f"/api/applications/{app['id']}/status", json={"status": "shared"}).status_code == 403  # the admin is the gate
    put = staff.post(f"/api/applications/{app['id']}/recommend", json={"note": "Strong Excel, ready to share."}).json()
    assert put["recommended_by"] == "staff1" and not put["can_recommend"]
    review = admin.get(f"/api/applications/{app['id']}/review").json()
    assert review["listing"]["opp_id"] == oid and review["match"]["eligible"] and review["student"]["student_id"] == "S004"
    assert admin.get(f"/api/applications?status=interested&opp_id={oid}").json()[0]["next"] == ["shared", "declined"]
    assert admin.post(f"/api/applications/{app['id']}/status", json={"status": "shared"}).json()["status"] == "shared"

    seen = acme.get(f"/api/me/listings/{oid}").json()["applicants"]
    assert len(seen) == 1 and re.fullmatch(r"[0-9a-f]{8}", seen[0]["candidate_code"]) and seen[0]["next"] == ["shortlisted", "not_a_fit"]
    blob = json.dumps(seen)
    assert "S004" not in blob and "student_id" not in blob and "name" not in blob.replace("candidate_code", "")
    assert seen[0]["student_note"].startswith("I know Excel")

    for to in ("shortlisted", "interview", "offered"):
        assert acme.post(f"/api/me/applications/{app['id']}/status", json={"status": to}).json()["status"] == to
    assert acme.post(f"/api/me/applications/{app['id']}/status", json={"status": "shared"}).status_code == 422   # no going back
    assert acme.post(f"/api/me/applications/{app['id']}/status", json={"status": "hired"}).json()["status"] == "hired"

    mine = next(a for a in stud.get("/api/me/applications").json() if a["id"] == app["id"])
    assert mine["status"] == "hired" and [e["to"] for e in mine["events"]] == ["interested", "shared", "shortlisted", "interview", "offered", "hired"]
    assert [e["by"] for e in mine["events"]][:3] == ["You", "The NGO", "The employer"]
    texts = [n["text"] for n in stud.get("/api/notifications").json()["items"]]
    assert any("shared your profile" in t for t in texts) and any("Congratulations" in t for t in texts)
    # one opening and one hire: the listing is full, so it closes and leaves matching
    assert staff.get(f"/api/opportunities/{oid}").status_code == 404
    assert acme.get(f"/api/me/listings/{oid}").json()["status"] == "closed"
    assert acme.post(f"/api/me/listings/{oid}/reopen").status_code == 422                            # filled listings stay closed


def test_a_student_cannot_apply_to_what_does_not_fit_or_is_not_open(make_client):
    stud, staff, acme = make_client("stud1"), make_client("staff1"), make_client("acme")
    why = staff.get("/api/students/S001/matches").json()["why_not"][0]
    r = stud.post("/api/me/applications", json={"opp_id": why["opp_id"]})
    assert r.status_code == 422 and "does not fit" in r.json()["detail"]
    pending = post(acme)["opp_id"]                                                                    # waiting for review: not open
    assert stud.post("/api/me/applications", json={"opp_id": pending}).status_code == 404
    assert stud.post("/api/me/applications", json={"opp_id": "NOPE"}).status_code == 404
    assert stud.post("/api/me/applications", json={"opp_id": why["opp_id"], "extra": 1}).status_code == 422


def test_decline_needs_a_reason_and_is_final(make_client):
    acme, ngo, stud = make_client("acme"), make_client("admin1"), make_client("pupil5")
    oid = live_listing(acme, ngo)
    app = stud.post("/api/me/applications", json={"opp_id": oid}).json()
    assert ngo.post(f"/api/applications/{app['id']}/status", json={"status": "declined"}).status_code == 422
    ok = ngo.post(f"/api/applications/{app['id']}/status", json={"status": "declined", "note": "Finish your final exams first."})
    assert ok.json()["status"] == "declined"
    mine = next(a for a in stud.get("/api/me/applications").json() if a["id"] == app["id"])
    assert mine["ngo_note"] == "Finish your final exams first." and not mine["can_withdraw"]
    assert stud.post("/api/me/applications", json={"opp_id": oid}).status_code == 422
    assert acme.get(f"/api/me/listings/{oid}").json()["applicants"] == []                            # never shared, so never visible


def test_withdraw_and_come_back_and_nobody_else_can_withdraw(make_client):
    acme, ngo, stud, other = make_client("acme"), make_client("admin1"), make_client("pupil6"), make_client("stud2")
    oid = live_listing(acme, ngo, openings=5)
    app = stud.post("/api/me/applications", json={"opp_id": oid}).json()
    assert other.post(f"/api/me/applications/{app['id']}/withdraw").status_code == 404
    assert stud.post(f"/api/me/applications/{app['id']}/withdraw").json()["status"] == "withdrawn"
    assert stud.post(f"/api/me/applications/{app['id']}/withdraw").status_code == 422
    assert stud.post("/api/me/applications", json={"opp_id": oid, "note": "Changed my mind"}).json()["status"] == "interested"


def test_a_busy_listing_is_marked_crowded_for_everyone(make_client):
    acme, ngo = make_client("acme"), make_client("admin1")
    oid = live_listing(acme, ngo, openings=1)                                                       # limit is 3 x 1 = 3 students
    st = deps.state()
    assert not st.row("S010", oid).crowded
    for u in ("stud1", "stud2", "pupil4", "pupil5"):
        assert make_client(u).post("/api/me/applications", json={"opp_id": oid}).status_code == 200
    st = deps.state()
    assert st.row("S010", oid).crowded and st.row("S010", oid).adjustments["crowded"] < 0      # state already follows the new load


def test_saved_listings(make_client):
    acme, ngo, stud = make_client("acme"), make_client("admin1"), make_client("stud2")
    oid = live_listing(acme, ngo, openings=5)
    assert stud.put(f"/api/me/saved/{oid}").json() == {"saved": True}
    assert [s["opp_id"] for s in stud.get("/api/me/saved").json()] == [oid]
    assert stud.put("/api/me/saved/NOPE").status_code == 404
    stud.delete(f"/api/me/saved/{oid}")
    assert stud.get("/api/me/saved").json() == []
    assert make_client("acme").get("/api/me/saved").status_code == 403


def test_staff_can_record_a_later_stage_for_an_employer(make_client):
    acme, ngo, stud = make_client("acme"), make_client("admin1"), make_client("pupil4")
    oid = live_listing(acme, ngo, openings=5)
    app = stud.post("/api/me/applications", json={"opp_id": oid}).json()
    ngo.post(f"/api/applications/{app['id']}/status", json={"status": "shared"})
    r = ngo.post(f"/api/applications/{app['id']}/status", json={"status": "interview", "note": "Employer called to say interview is set."})
    assert r.json()["status"] == "interview"
    assert acme.get(f"/api/me/listings/{oid}").json()["applicants"][0]["status"] == "interview"


def test_my_matches_show_application_status_and_saved(make_client):
    acme, ngo, stud = make_client("acme"), make_client("admin1"), make_client("stud2")
    oid = live_listing(acme, ngo, openings=5, required_skills_text="Python, SQL, Git")
    assert stud.post("/api/me/applications", json={"opp_id": oid}).status_code in (200, 422)
    cards = stud.get("/api/me/student").json()["matches"]
    assert all({"application", "saved", "fit", "gap_closers"} <= set(c) for c in cards)


def test_browse_lists_every_live_listing_with_fit_and_blockers(make_client):
    acme, ngo, stud = make_client("acme"), make_client("admin1"), make_client("stud1")
    oid = live_listing(acme, ngo, openings=5, title="Browsable Remote Analyst")
    items = stud.get("/api/me/browse").json()
    assert len(items) >= 50 and any(i["opp_id"] == oid for i in items)
    fits = [i for i in items if i["eligible"]]
    assert fits and all(not i["blockers"] for i in fits) and any(i["blockers"] for i in items if not i["eligible"])
    assert [i["eligible"] for i in items] == sorted((i["eligible"] for i in items), reverse=True)     # ones you can take come first
    scores = [i["score"] for i in fits]
    assert scores == sorted(scores, reverse=True)
    assert {"fit", "application", "saved", "description"} <= set(items[0])
    pending = post(acme)["opp_id"]
    assert all(i["opp_id"] != pending for i in stud.get("/api/me/browse").json())                  # not live: not listed
    assert make_client("acme").get("/api/me/browse").status_code == 403
    assert make_client().get("/api/me/browse").status_code == 401


def test_a_student_can_read_a_live_listing_in_full_before_showing_interest(make_client):
    stud, staff, acme = make_client("stud1"), make_client("staff1"), make_client("acme")
    before = stud.get("/api/me/applications").json()
    d = stud.get("/api/me/browse/J028").json()
    assert stud.get("/api/me/applications").json() == before                     # reading is not showing interest
    assert d["title"] == "Data Analyst Trainee" and isinstance(d["description"], str)
    assert set(d["overlap"]) | set(d["missing"]) <= set(d["skills"]) and d["languages_required"] and d["openings"] >= 1
    assert {"hours_per_week", "night_shift", "blockers", "checks", "gap_closers", "nice", "related"} <= d.keys()
    assert not re.search(r"\bS(?!001\b)\d{3}\b", json.dumps(d))                   # nothing about other students
    assert all(x["credit"] >= 0.5 for x in d["related"])

    draft = post(acme, {"title": "Draft Analyst"}, submit=False)["opp_id"]
    in_review = post(acme, {"title": "Pending Analyst"})["opp_id"]
    assert stud.get(f"/api/me/browse/{draft}").status_code == 404
    assert stud.get(f"/api/me/browse/{in_review}").status_code == 404
    approve(make_client("admin1"), in_review)                                   # only admins approve listings (#18)
    live = stud.get(f"/api/me/browse/{in_review}").json()
    assert live["title"] == "Pending Analyst" and live["description"] == "Work on dashboards."

    assert stud.get("/api/me/browse/NOPE").status_code == 404
    assert staff.get("/api/me/browse/J028").status_code == 403 and acme.get("/api/me/browse/J028").status_code == 403


def test_a_listing_the_student_cannot_take_says_why(make_client):
    stud = make_client("stud1")
    blocked = next(i for i in stud.get("/api/me/browse").json() if not i["eligible"])
    d = stud.get(f"/api/me/browse/{blocked['opp_id']}").json()
    assert not d["eligible"] and d["blockers"] == blocked["blockers"]


def test_the_listing_page_shows_the_last_day_and_closes_with_it(make_client):
    """#17's listing page and #18's deadlines together: the page carries the dates, and a passed last day reads as closed,
    just as showing interest is refused then."""
    from datetime import date, timedelta

    from api import deps
    stud, admin = make_client("stud1"), make_client("admin1")
    soon = (date.today() + timedelta(days=2)).isoformat()
    oid = admin.post("/api/listings", json={**GOOD, "title": "Deadline Analyst", "apply_by": soon, "owner_username": "acme"}).json()["opp_id"]
    d = stud.get(f"/api/me/browse/{oid}").json()
    assert d["apply_by"] == soon and d["closing_soon"] is True and {"starts_on", "duration_weeks"} <= d.keys()
    row = next(i for i in stud.get("/api/me/browse").json() if i["opp_id"] == oid)
    assert row["apply_by"] == d["apply_by"] and row["closing_soon"] == d["closing_soon"]        # Browse and the page agree

    st = deps.state()
    st.opps = {**st.opps, oid: st.opps[oid].model_copy(update={"apply_by": "2020-01-01"})}   # passed, before any sweep runs
    assert stud.get(f"/api/me/browse/{oid}").status_code == 404
    deps.reset_state()


def test_the_student_lifeline_knows_the_ngo_review_and_where_an_application_stopped(make_client):
    acme, staff, admin, stud = make_client("acme"), make_client("staff1"), make_client("admin1"), make_client("pupil6")
    oid = live_listing(acme, admin, openings=5)
    app = stud.post("/api/me/applications", json={"opp_id": oid}).json()
    mine = lambda: next(a for a in stud.get("/api/me/applications").json() if a["id"] == app["id"])   # noqa: E731
    assert mine()["reviewing"] is False and "stopped_at" not in mine()
    staff.post(f"/api/applications/{app['id']}/recommend", json={"note": "Ready to share."})
    seen = mine()
    assert seen["reviewing"] is True and "staff1" not in json.dumps(seen)                      # never says which staff member
    admin.post(f"/api/applications/{app['id']}/status", json={"status": "shared"})
    assert mine()["reviewing"] is False and mine()["status"] == "shared"
    stud.post(f"/api/me/applications/{app['id']}/withdraw", json={"note": "Found another job"})
    assert mine()["status"] == "withdrawn" and mine()["stopped_at"] == "shared"
