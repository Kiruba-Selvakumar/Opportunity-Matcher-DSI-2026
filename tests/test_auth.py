from datetime import timedelta

import pytest

from matcher import accounts, audit, auth, store


@pytest.fixture
def db(tmp_path):
    auth.ip_reset()
    return tmp_path / "t.db"


def make(db, username="officer1", role="ngo_staff", password="correct horse battery", **kw):
    return accounts.create_user(username, username.title(), role, password=password, must_change=False, path=db, **kw)[0]


def test_hash_and_verify():
    h = auth.hash_password("correct horse battery")
    assert h.startswith("scrypt$") and "correct" not in h
    assert auth.verify_password("correct horse battery", h)
    assert not auth.verify_password("wrong", h)
    assert not auth.verify_password("x", "garbage")
    assert auth.hash_password("same") != auth.hash_password("same")  # random salt


def test_old_parameters_are_rehashed_on_login(db):
    u = make(db)
    weak = auth.hash_password("correct horse battery", n=2**12)
    c = store.connect(db)
    c.execute("UPDATE users SET password_hash = ? WHERE id = ?", (weak, u.id))
    assert auth.needs_rehash(weak)
    accounts.authenticate("officer1", "correct horse battery", path=db)
    new = store.connect(db).execute("SELECT password_hash FROM users").fetchone()[0]
    assert not auth.needs_rehash(new)


@pytest.mark.parametrize("pw,msg", [("short1", "at least 10"), ("password123", "too common"), ("x" * 129, "at most 128")])
def test_policy_rejections(pw, msg):
    with pytest.raises(auth.AuthError, match=msg):
        auth.check_password_policy(pw, "officer1")


def test_policy_rejects_username_as_password_and_accepts_a_good_one():
    with pytest.raises(auth.AuthError, match="same as the username"):
        auth.check_password_policy("Officer12345", "officer12345")
    auth.check_password_policy("a perfectly fine passphrase", "officer1")


def test_wrong_password_and_unknown_user_give_the_same_message(db):
    make(db)
    with pytest.raises(auth.AuthError) as a:
        accounts.authenticate("officer1", "nope nope nope", path=db)
    with pytest.raises(auth.AuthError) as b:
        accounts.authenticate("nobody", "nope nope nope", path=db)
    assert a.value.public == b.value.public == "Wrong username or password."


def test_lockout_after_five_failures_then_unlock(db):
    make(db)
    for _ in range(5):
        with pytest.raises(auth.AuthError):
            accounts.authenticate("officer1", "bad bad bad bad", path=db)
    with pytest.raises(auth.AuthError, match="locked"):  # even the right password is refused
        accounts.authenticate("officer1", "correct horse battery", path=db)
    c = store.connect(db)
    c.execute("UPDATE users SET locked_until = ?", (auth.iso(auth.now() - timedelta(minutes=1)),))
    assert accounts.authenticate("officer1", "correct horse battery", path=db).username == "officer1"
    actions = [e["action"] for e in audit.list_events(path=db)]
    assert "login.locked" in actions and "login.ok" in actions


def test_deactivated_cannot_sign_in(db):
    u = make(db)
    make(db, "admin1", "ngo_admin")
    accounts.set_active(u.id, False, db)
    with pytest.raises(auth.AuthError):
        accounts.authenticate("officer1", "correct horse battery", path=db)


def test_session_lifecycle_expiry_and_revoke(db, monkeypatch):
    u = make(db)
    c = store.connect(db)
    token, csrf = auth.create_session(c, u.id, "1.2.3.4")
    assert "sha" not in token and c.execute("SELECT token_hash FROM sessions").fetchone()[0] != token  # only the hash is stored
    assert auth.load_session(c, token) is not None
    assert auth.load_session(c, "forged") is None and auth.load_session(c, None) is None
    # idle timeout
    assert auth.load_session(c, token, auth.now() + timedelta(hours=2, minutes=1)) is None
    assert c.execute("SELECT COUNT(*) FROM sessions").fetchone()[0] == 0
    # absolute timeout, even with steady use
    t0 = auth.now()
    token, _ = auth.create_session(c, u.id, at=t0)
    for h in (1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11):
        assert auth.load_session(c, token, t0 + timedelta(hours=h, minutes=30 * 0)) is not None
    assert auth.load_session(c, token, t0 + timedelta(hours=12, minutes=1)) is None
    # revoke keeps one
    t1, _ = auth.create_session(c, u.id)
    t2, _ = auth.create_session(c, u.id)
    assert auth.revoke_sessions(c, u.id, keep_token=t1) == 1
    assert auth.load_session(c, t1) is not None and auth.load_session(c, t2) is None


def test_csrf_compare():
    assert auth.csrf_ok("abc", "abc") and not auth.csrf_ok("abc", "abd") and not auth.csrf_ok("abc", None)


def test_ip_throttle():
    auth.ip_reset()
    for i in range(20):
        assert auth.ip_allowed("9.9.9.9", at=1000 + i)
        auth.ip_note_attempt("9.9.9.9", at=1000 + i)
    assert not auth.ip_allowed("9.9.9.9", at=1030)
    assert auth.ip_allowed("9.9.9.9", at=1000 + 601 + 19)  # window has passed
