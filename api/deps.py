"""Things every route file needs: the live state, who is signed in, and how to write an audit row."""
from __future__ import annotations

from fastapi import HTTPException

from matcher import audit, notifications

from . import helpers
from .security import Session

_state: helpers.State | None = None
_swept = 0.0
SWEEP_SECONDS = 60


def state() -> helpers.State:
    global _state
    if _state is None:
        try:
            _state = helpers.load_state()
        except helpers.NotReady as e:
            raise HTTPException(503, str(e))
    sweep(_state)
    return _state


def sweep(st: helpers.State, force: bool = False) -> list[str]:
    """At most once a minute: close listings whose last day to apply has passed, and tell the people involved."""
    global _swept
    import time
    if not force and time.monotonic() - _swept < SWEEP_SECONDS:
        return []
    _swept = time.monotonic()
    from matcher import applications, listings
    gone = listings.close_expired()
    for oid in gone:
        st.sync_listing(oid)
        tell(notifications.owner_user_ids(oid), "review", "A listing closed because its last day to apply passed.", f"/employer/{oid}")
        for a in applications.list_apps(opp_id=oid, statuses=("interested",)):
            tell(notifications.student_user_id(a["student_id"]), "application", "A listing you asked about closed: the last day to apply passed.", "/student/applications")
    for oid in st.drop_expired():
        gone.append(oid)
        for a in applications.list_apps(opp_id=oid, statuses=("interested",)):
            tell(notifications.student_user_id(a["student_id"]), "application", "A listing you asked about closed: the last day to apply passed.", "/student/applications")
    return gone


def reset_state() -> None:
    global _state, _swept
    _state = None
    _swept = 0.0


def student_or_404(sid: str) -> helpers.State:
    st = state()
    if sid not in st.students:
        raise HTTPException(404, "Not found.")
    return st


def who(sess: Session) -> dict:
    return {"id": sess.user.id, "username": sess.user.username, "role": sess.user.role}


def log(action: str, sess: Session, target: str | None = None, detail: str | None = None) -> None:
    audit.record(action, user=who(sess), target=target, ip=sess.ip, detail=detail)


def known_names() -> list[str]:
    return list(state().contacts.values())


def tell(user_ids: list[int] | int | None, kind: str, text: str, link: str | None = None) -> None:
    """Write a notification. The text must never hold names, contact details or message text."""
    if user_ids is None or user_ids == []:
        return
    notifications.add(user_ids, kind, text, link)
