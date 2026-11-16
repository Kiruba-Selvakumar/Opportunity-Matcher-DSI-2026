import itertools

import pytest

from matcher import accounts, applications as ap, notifications as nt
from matcher.applications import ApplicationError


@pytest.fixture
def db(tmp_path):
    return tmp_path / "t.db"


def mk(db, sid="S001", opp="J001", note=""):
    return ap.create(sid, opp, note, path=db)


def test_create_and_duplicates(db):
    a = mk(db, note="Call me 9876543210")
    assert a["status"] == "interested" and "9876543210" not in a["student_note"]
    with pytest.raises(ApplicationError, match="already"):
        mk(db)
    assert [e["to_status"] for e in ap.events(a["id"], db)] == ["interested"]


def test_the_full_happy_path_by_role(db):
    a = mk(db)
    for role, to in [("ngo", "shared"), ("lister", "shortlisted"), ("lister", "interview"), ("lister", "offered"), ("lister", "hired")]:
        a = ap.transition(a["id"], to, role, path=db)
    assert a["status"] == "hired"
    evs = ap.events(a["id"], db)
    assert [e["to_status"] for e in evs] == ["interested", "shared", "shortlisted", "interview", "offered", "hired"]
    assert [e["actor_role"] for e in evs] == ["student", "ngo", "lister", "lister", "lister", "lister"]


@pytest.mark.parametrize("role,frm,to,ok", [
    ("student", None, "interested", True), ("student", "interested", "withdrawn", True), ("student", "offered", "withdrawn", True),
    ("student", "hired", "withdrawn", False), ("student", "interested", "shared", False), ("student", "shared", "hired", False),
    ("ngo", "interested", "shared", True), ("ngo", "interested", "declined", True), ("ngo", "interested", "hired", False),
    ("ngo", "shared", "interview", True), ("ngo", "offered", "not_a_fit", True), ("ngo", "hired", "shared", False),
    ("lister", "interested", "shared", False), ("lister", "shared", "shortlisted", True), ("lister", "shared", "interview", False),
    ("lister", "shared", "not_a_fit", True), ("lister", "offered", "hired", True), ("lister", "hired", "not_a_fit", False),
    ("lister", "declined", "shared", False), ("nobody", "interested", "shared", False),
])
def test_transition_rules(role, frm, to, ok):
    assert ap.allowed(role, frm, to) is ok


def test_a_reason_is_needed_to_close_and_nothing_goes_backwards(db):
    a = mk(db)
    with pytest.raises(ApplicationError, match="reason"):
        ap.transition(a["id"], "declined", "ngo", path=db)
    d = ap.transition(a["id"], "declined", "ngo", note="Needs a degree certificate first", path=db)
    assert d["status"] == "declined" and d["ngo_note"].startswith("Needs")
    with pytest.raises(ApplicationError):
        ap.transition(a["id"], "shared", "ngo", path=db)
    with pytest.raises(ApplicationError, match="closed"):
        mk(db)                                                          # a declined one cannot be reopened by the student


def test_withdraw_and_come_back(db):
    a = mk(db)
    ap.transition(a["id"], "withdrawn", "student", path=db)
    back = mk(db, note="I changed my mind")
    assert back["id"] == a["id"] and back["status"] == "interested"
    assert [e["to_status"] for e in ap.events(a["id"], db)] == ["interested", "withdrawn", "interested"]


def test_load_funnel_and_hired_counts(db):
    for i, sid in enumerate(["S001", "S002", "S003"]):
        a = mk(db, sid=sid)
        if i < 2:
            a = ap.transition(a["id"], "shared", "ngo", path=db)
        if i < 1:
            ap.transition(a["id"], "shortlisted", "lister", path=db)
    assert ap.load_by_listing(db) == {"J001": 3}
    f = ap.funnel(db)
    assert (f["interested"], f["shared"], f["shortlisted"], f["hired"]) == (3, 2, 1, 0)
    ap.transition(1, "interview", "ngo", path=db); ap.transition(1, "offered", "ngo", path=db); ap.transition(1, "hired", "ngo", path=db)
    assert ap.hired_count("J001", db) == 1 and ap.load_by_listing(db) == {"J001": 2}


def test_saved_listings(db):
    ap.save("S001", "J001", db); ap.save("S001", "J002", db); ap.save("S001", "J001", db)
    assert sorted(ap.saved("S001", db)) == ["J001", "J002"]
    ap.unsave("S001", "J001", db)
    assert ap.saved("S001", db) == ["J002"]
    mk(db, opp="J002")                                                   # showing interest removes it from saved
    assert ap.saved("S001", db) == []


def test_notifications(db):
    a, _ = accounts.create_user("stud9", "S", "student", student_id="S009", password="a long test password", must_change=False, path=db)
    b, _ = accounts.create_user("off9", "O", "ngo_staff", password="a long test password", must_change=False, path=db)
    c, _ = accounts.create_user("emp9", "E", "employer", listings=["J009"], password="a long test password", must_change=False, path=db)
    assert nt.ngo_user_ids(db) == [b.id] and nt.owner_user_ids("J009", db) == [c.id] and nt.student_user_id("S009", db) == a.id
    assert nt.add([a.id, a.id, b.id], "x", "Your application moved", "/student/applications", db) == 2   # duplicates are dropped
    assert nt.unread(a.id, db) == 1 and nt.unread(b.id, db) == 1
    first = nt.list_for(a.id, path=db)[0]
    assert nt.mark_read(b.id, first["id"], db) is False                  # not theirs
    assert nt.mark_read(a.id, first["id"], db) is True and nt.unread(a.id, db) == 0
    nt.add(a.id, "x", "Another", None, db)
    assert nt.mark_all(a.id, db) == 1 and nt.unread(a.id, db) == 0
