"""Bulk WhatsApp to students: a new listing to the students it fits best, "your matches are ready", or an NGO update.

A broadcast is planned first (who would get it, and who cannot be reached), then sent as one batch. Only students who
agreed to WhatsApp and have a usable number get a message. Each template must be approved in Meta first (README).
"""
from __future__ import annotations

from datetime import date
from typing import Callable

from . import config, contacts, outbox, settings, standins, whatsapp
from .privacy import redact
from .schema import MatchRow, Opportunity, Student, TopMatch

KINDS = ("opportunity", "matches", "update")
MAX_TEXT = 300


def _apply_by_words(o: Opportunity) -> str:
    if not o.apply_by:
        return "soon"
    return date.fromisoformat(o.apply_by).strftime("%d %b %Y")


def _keep(s: Student, program: str | None, branch: str | None) -> bool:
    return (not program or s.program == program) and (not branch or s.branch == branch)


def plan(kind: str, students: dict[str, Student], *, rows_for_opp: list[MatchRow] | None = None, opp: Opportunity | None = None,
         matches_of: Callable[[str], list[TopMatch]] | None = None, program: str | None = None, branch: str | None = None,
         text: str = "", min_score: float = config.MIN_SHOW_SCORE, limit: int = 200,
         known_names: list[str] | None = None) -> dict:
    """Who a broadcast would reach. Nothing is sent."""
    if kind not in KINDS:
        raise ValueError("Unknown kind of message.")
    link = f"{settings.app_url()}/student"
    people: list[dict] = []
    if kind == "opportunity":
        if opp is None or rows_for_opp is None:
            raise ValueError("Pick a listing.")
        rows = sorted((r for r in rows_for_opp if r.eligible and r.final_score >= min_score), key=lambda r: (-r.final_score, r.student_id))
        o_link = f"{settings.app_url()}/student/browse?opp={opp.opp_id}"
        params = [opp.title, opp.org_name, _apply_by_words(opp), o_link]
        for r in rows:
            if _keep(students[r.student_id], program, branch):
                people.append({"student_id": r.student_id, "score": r.final_score, "params": params,
                               "preview": f"A new {opp.title} opportunity at {opp.org_name} fits your profile. "
                                          f"Apply by {params[2]}. See it here: {o_link}"})
    elif kind == "matches":
        if matches_of is None:
            raise ValueError("No matches to send.")
        for sid, s in sorted(students.items()):
            if not _keep(s, program, branch):
                continue
            ms = matches_of(sid)
            if ms:
                people.append({"student_id": sid, "params": [str(len(ms)), ms[0].title, link],
                               "preview": f"You have {len(ms)} matches waiting. The best one right now is {ms[0].title}. Open: {link}"})
    else:
        body = redact(" ".join((text or "").split()), known_names or [])
        if not body:
            raise ValueError("Write the update first.")
        if len(body) > MAX_TEXT:
            raise ValueError(f"Keep the update under {MAX_TEXT} characters.")
        for sid, s in sorted(students.items()):
            if _keep(s, program, branch):
                people.append({"student_id": sid, "params": [body, link], "preview": f"Update from the NGO: {body} Open: {link}"})
    people = people[:max(1, min(limit, 1000))]
    agreed = contacts.opted_in()
    reachable = [p for p in people if p["student_id"] in agreed and contacts.phone(p["student_id"])]
    return {"kind": kind, "total": len(people), "reachable": len(reachable),
            "not_agreed": sum(1 for p in people if p["student_id"] not in agreed),
            "no_phone": sum(1 for p in people if p["student_id"] in agreed and not contacts.phone(p["student_id"])),
            "preview": people[0]["preview"] if people else "", "recipients": reachable,
            "sample": [{"student_id": p["student_id"], "score": p.get("score")} for p in people[:20]],
            "live": settings.whatsapp() is not None,
            "stand_ins": sum(1 for p in reachable if standins.whatsapp_for_student(p["student_id"])) if standins.active() else None}


def send(planned: dict) -> dict:
    """Send a planned broadcast as one batch. Returns the batch id and how many were queued."""
    batch = outbox.new_batch()
    queued = 0
    for p in planned["recipients"]:
        if whatsapp.send_template(p["student_id"], planned["kind"], p["params"], p["preview"], batch_id=batch) is not None:
            queued += 1
    return {"batch_id": batch, "queued": queued, "live": planned["live"]}
