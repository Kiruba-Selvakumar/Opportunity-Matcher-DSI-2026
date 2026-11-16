import pytest

from matcher import accounts, auth, store


@pytest.fixture
def db(tmp_path):
    return tmp_path / "t.db"


def test_create_with_temp_password_forces_change(db):
    u, temp = accounts.create_user("S001", "Lakshmi", "student", student_id="S001", path=db)
    assert u.username == "s001" and temp and len(temp) == 16 and u.must_change_password
    assert accounts.authenticate("s001", temp, path=db).must_change_password


def test_validation(db):
    bad = [dict(username="ab", role="ngo_staff"), dict(username="has space", role="ngo_staff"),
           dict(username="x" * 33, role="ngo_staff"), dict(username="okname", role="king"),
           dict(username="okname", role="student"),
           dict(username="okname", role="ngo_staff", student_id="S1")]
    for kw in bad:
        with pytest.raises(auth.AuthError):
            accounts.create_user(kw.pop("username"), "Name", kw.pop("role"), path=db, **kw)
    accounts.create_user("dup1", "A", "ngo_staff", path=db)
    with pytest.raises(auth.AuthError, match="taken"):
        accounts.create_user("DUP1", "B", "ngo_staff", path=db)
    accounts.create_user("stud1", "A", "student", student_id="S1", path=db)
    with pytest.raises(auth.AuthError, match="already has an account"):
        accounts.create_user("stud1b", "B", "student", student_id="S1", path=db)


def test_employer_listings(db):
    u, _ = accounts.create_user("acme", "Acme", "employer", listings=["J1", "J2", "J1"], path=db)
    assert u.listings == ["J1", "J2"]
    accounts.set_listings(u.id, ["J3"], db)
    assert accounts.get_user(u.id, db).listings == ["J3"]
    s, _ = accounts.create_user("stud", "S", "student", student_id="S9", path=db)
    with pytest.raises(auth.AuthError):
        accounts.set_listings(s.id, ["J1"], db)


def test_change_password_rules_and_revokes_other_sessions(db):
    u, temp = accounts.create_user("officer1", "O", "ngo_staff", path=db)
    c = store.connect(db)
    keep, _ = auth.create_session(c, u.id)
    other, _ = auth.create_session(c, u.id)
    with pytest.raises(auth.AuthError, match="current password is wrong"):
        accounts.change_password(u.id, "nope", "a brand new password", path=db)
    with pytest.raises(auth.AuthError, match="too common"):
        accounts.change_password(u.id, temp, "password123", path=db)
    with pytest.raises(auth.AuthError, match="different"):
        accounts.change_password(u.id, temp, temp, path=db)
    accounts.change_password(u.id, temp, "a brand new password", keep_token=keep, path=db)
    assert not accounts.get_user(u.id, db).must_change_password
    c = store.connect(db)
    assert auth.load_session(c, keep) is not None and auth.load_session(c, other) is None
    assert accounts.authenticate("officer1", "a brand new password", path=db)


def test_reset_password_and_last_admin_protection(db):
    admin, _ = accounts.create_user("admin1", "A", "ngo_admin", password="long enough password", path=db)
    with pytest.raises(auth.AuthError, match="last active admin"):
        accounts.set_active(admin.id, False, db)
    second, _ = accounts.create_user("admin2", "B", "ngo_admin", path=db)
    accounts.set_active(admin.id, False, db)  # now allowed
    temp = accounts.reset_password(second.id, db)
    u = accounts.authenticate("admin2", temp, path=db)
    assert u.must_change_password
    with pytest.raises(auth.AuthError):
        accounts.reset_password(9999, db)


def test_bootstrap_admin_only_when_empty(db, monkeypatch):
    monkeypatch.setenv("BOOTSTRAP_ADMIN_USERNAME", "root1")
    monkeypatch.setenv("BOOTSTRAP_ADMIN_PASSWORD", "a long bootstrap password")
    assert accounts.bootstrap_admin_if_empty(db) is True
    assert accounts.bootstrap_admin_if_empty(db) is False
    u = accounts.get_by_username("root1", db)
    assert u.role == "ngo_admin" and u.must_change_password


def test_seed_demo_refuses_in_secure_mode(monkeypatch, capsys):
    monkeypatch.setenv("COOKIE_SECURE", "1")
    monkeypatch.setenv("DEMO_PASSWORD", "a long demo password")
    assert accounts.main(["seed-demo"]) == 1
    assert "Refusing" in capsys.readouterr().err


def test_seed_demo_gives_the_ngo_something_to_do(db, monkeypatch):
    from matcher import applications, contacts, listings
    from matcher.config import PATHS
    monkeypatch.setenv("DEMO_PASSWORD", "a long demo password")
    monkeypatch.setitem(PATHS, "db", db)            # every call passes path=None, which reads PATHS: never the real database
    assert accounts.main(["seed-demo"]) == 0
    assert [r["status"] for r in listings.list_all()] == ["pending"]
    assert [a["status"] for a in applications.list_apps()] == ["interested"]
    assert contacts.opted_in() == {"S001", "S002", "S003"}
    assert accounts.get_by_username("gopuram").email == "hr@gopuram.example.com"
    assert accounts.main(["seed-demo"]) == 0                                    # running it again changes nothing
    assert len(listings.list_all()) == 1 and len(applications.list_apps()) == 1
