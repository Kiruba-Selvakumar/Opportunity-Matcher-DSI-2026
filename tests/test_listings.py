import pytest
from pydantic import ValidationError

from matcher import accounts, listings
from matcher.listings import ListingError, ListingIn


@pytest.fixture
def db(tmp_path):
    p = tmp_path / "t.db"
    u, _ = accounts.create_user("acme1", "Acme", "employer", password="a long test password", listings=["J001"], must_change=False, path=p)
    v, _ = accounts.create_user("other1", "Other", "employer", password="a long test password", listings=["J002"], must_change=False, path=p)
    return p, u.id, v.id


def body(**kw):
    base = dict(title="Junior Data Analyst", org_name="Acme Data", required_skills_text="Excel, SQL, Power BI is a plus",
                city="Hyderabad", mode="onsite", pay_text="3.6 LPA", hours_per_week=40, openings=2)
    base.update(kw)
    return ListingIn(**base)


def test_validation_limits():
    for bad in [dict(title="ab"), dict(title="x" * 81), dict(hours_per_week=0), dict(hours_per_week=81), dict(openings=0),
                dict(openings=51), dict(description="x" * 1001), dict(required_skills_text="x"), dict(city=""),
                dict(city="Remote"), dict(languages=[]), dict(type="intern"), dict(apply_by="30-11-2026"),
                dict(starts_on="soon"), dict(duration_weeks=0), dict(batch_every_weeks=53)]:
        with pytest.raises(ValidationError):
            body(**bad)
    with pytest.raises(ValidationError):
        ListingIn(**{**body().model_dump(), "surprise": 1})
    assert body(mode="remote", city="Pune").city == "Remote"          # remote always means Remote


def test_create_draft_submit_and_ids(db):
    p, uid, _ = db
    a = listings.create(uid, body(), path=p)
    b = listings.create(uid, body(title="Second role"), submit=True, path=p)
    assert (a["opp_id"], a["status"], b["opp_id"], b["status"]) == ("E001", "draft", "E002", "pending")
    assert listings.submit("E001", uid, p)["status"] == "pending"
    with pytest.raises(ListingError):
        listings.submit("E001", uid, p)                                 # already pending


def test_review_flow_and_rules(db):
    p, uid, _ = db
    listings.create(uid, body(), submit=True, path=p)
    with pytest.raises(ListingError, match="why"):
        listings.review("E001", "officer", "reject", 3, "", p)
    with pytest.raises(ListingError):
        listings.review("E001", "officer", "approve", 9, "", p)
    r = listings.review("E001", "officer", "approve", 4, "Looks fine", p)
    assert r["status"] == "active" and r["safety_score"] == 4 and r["was_approved"] == 1 and r["reviewed_by"] == "officer"
    with pytest.raises(ListingError):
        listings.review("E001", "officer", "approve", 4, "", p)         # no longer pending


def test_edit_sends_active_back_to_review_and_reopen_rules(db):
    p, uid, other = db
    listings.create(uid, body(), submit=True, path=p)
    listings.review("E001", "o", "approve", 4, "", p)
    edited = listings.update("E001", uid, body(title="Senior Data Analyst"), submit=True, path=p)
    assert edited["status"] == "pending" and edited["edited_since_review"] == 1
    with pytest.raises(ListingError):
        listings.update("E001", other, body(), path=p)                  # not the owner
    listings.review("E001", "o", "approve", 4, "", p)
    listings.close("E001", uid, path=p)
    assert listings.reopen("E001", uid, p)["status"] == "active"        # approved and unchanged: straight back
    listings.close("E001", uid, path=p)
    listings.update("E001", uid, body(title="Changed again"), path=p)
    assert listings.reopen("E001", uid, p)["status"] == "pending"       # changed since review: review again


def test_filled_listing_cannot_be_reopened_and_copy_makes_a_draft(db):
    p, uid, _ = db
    listings.create(uid, body(), submit=True, path=p)
    listings.close("E001", None, reason="filled", path=p)
    with pytest.raises(ListingError, match="filled"):
        listings.reopen("E001", uid, p)
    c = listings.copy("E001", uid, path=p)
    assert c["status"] == "draft" and c["opp_id"] == "E002" and c["data"]["title"].endswith("(copy)")


def test_to_opportunity_matches_the_pipeline_shape(db):
    p, uid, _ = db
    row = listings.create(uid, body(upfront_cost_text="Rs 12,000", night_shift=True), path=p)
    opp = listings.to_opportunity({**row, "safety_score": 4})
    assert opp.opp_id == "E001" and opp.upfront_cost == 12000 and opp.night_shift and opp.safety_score == 4
    assert opp.pay_min == 360000 and opp.nice_to_have == ["power bi"] and opp.openings == 2
    assert "power bi" in opp.required_skills_raw
    remote = listings.to_opportunity(listings.create(uid, body(mode="remote"), path=p))
    assert remote.city == "Remote" and remote.mode == "remote"


def test_review_flags(db):
    p, uid, _ = db
    clean = listings.create(uid, body(), path=p)
    assert listings.review_flags(clean, mapped_skills=3) == []
    bad = listings.create(uid, body(upfront_cost_text="5k", description="Message us on WhatsApp 9876543210", night_shift=True,
                                    hours_per_week=60, pay_text=""), path=p)
    flags = listings.review_flags(bad, mapped_skills=0)
    texts = " | ".join(f["text"] for f in flags)
    assert [f["level"] for f in flags].count("red") == 2
    for part in ("up front", "outside the system", "night", "60 hours", "Pay is missing", "skill list"):
        assert part in texts


def test_text_is_redacted(db):
    p, uid, _ = db
    row = listings.create(uid, body(description="Ask Lakshmi on 9876543210 or a@b.com"), known_names=["Lakshmi Prasanna"], path=p)
    d = row["data"]["description"]
    assert "9876543210" not in d and "a@b.com" not in d and "Lakshmi" not in d


def test_deadline_rules_and_closing_when_it_passes(db):
    from datetime import date, timedelta
    p, owner, _ = db
    soon = (date.today() + timedelta(days=3)).isoformat()
    with pytest.raises(ListingError, match="already passed"):
        listings.create(owner, body(apply_by=(date.today() - timedelta(days=1)).isoformat()), path=p)
    row = listings.create(owner, body(apply_by=soon), submit=True, path=p)
    listings.review(row["opp_id"], "admin1", "approve", 4, path=p)
    assert listings.to_opportunity(listings.get(row["opp_id"], p)).apply_by == soon
    assert listings.close_expired(today=date.today(), path=p) == []
    assert listings.close_expired(today=date.today() + timedelta(days=4), path=p) == [row["opp_id"]]
    gone = listings.get(row["opp_id"], p)
    assert gone["status"] == "closed" and "last day" in gone["closed_reason"]


def test_training_schedule_and_mentor_shape(db):
    p, owner, _ = db
    t = listings.create(owner, body(type="training", title="SQL Basics", starts_on="2026-11-02", duration_weeks=6, batch_every_weeks=4), path=p)
    o = listings.to_opportunity(t)
    assert (o.type, o.starts_on, o.duration_weeks, o.batch_every_weeks) == ("training", "2026-11-02", 6, 4)
    j = listings.create(owner, body(starts_on="2026-11-02", duration_weeks=6), path=p)        # a job has no batches
    assert listings.to_opportunity(j).starts_on is None
    m = listings.create(owner, body(type="mentor", title="Alumni mentor: SQL", mode="remote"), path=p, link_owner=False)
    assert listings.to_opportunity(m).job_family == "Mentorship" and m["opp_id"] not in accounts.get_user(owner, p).listings


def test_ngo_edit_keeps_a_live_listing_live(db):
    p, owner, _ = db
    row = listings.create(owner, body(), submit=True, path=p)
    listings.review(row["opp_id"], "admin1", "approve", 4, path=p)
    after = listings.ngo_edit(row["opp_id"], body(title="Senior Data Analyst"), path=p)
    assert after["status"] == "active" and after["data"]["title"] == "Senior Data Analyst"
    with pytest.raises(ListingError):
        listings.ngo_edit("E999", body(), path=p)
