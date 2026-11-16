"""Notifications and the list of places someone is signed in."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from matcher import auth, notifications, store

from ..deps import log
from ..security import Session, get_session

router = APIRouter()


@router.get("/api/notifications")
def my_notifications(sess: Session = Depends(get_session)):
    return {"unread": notifications.unread(sess.user.id), "items": notifications.list_for(sess.user.id)}


@router.post("/api/notifications/read-all")
def read_all(sess: Session = Depends(get_session)):
    return {"marked": notifications.mark_all(sess.user.id)}


@router.post("/api/notifications/{notification_id}/read")
def read_one(notification_id: int, sess: Session = Depends(get_session)):
    if not notifications.mark_read(sess.user.id, notification_id):
        raise HTTPException(404, "Not found.")
    return {"ok": True}


@router.get("/api/auth/sessions")
def my_sessions(sess: Session = Depends(get_session)):
    conn = store.connect()
    try:
        return auth.list_sessions(conn, sess.user.id, sess.token)
    finally:
        conn.close()


@router.post("/api/auth/sessions/revoke-others")
def revoke_others(sess: Session = Depends(get_session)):
    conn = store.connect()
    try:
        n = auth.revoke_sessions(conn, sess.user.id, keep_token=sess.token)
    finally:
        conn.close()
    log("sessions.revoked", sess, detail=f"{n} other sign-ins")
    return {"revoked": n}
