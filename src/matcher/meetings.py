"""Scheduling an interview end to end: the calendar invite, the Meet link, the notetaker, and the notes afterwards.

With Google connected, the event goes on the NGO calendar with a Meet link and Google sends the invites. Without it (or if
Google fails), everyone gets an email with a calendar file and the link staff typed. The Fireflies bot is invited when
the interviewer asks for notes, so it records even when nobody from the NGO joins. The student hears about it in the app
and, if they agreed, on WhatsApp. Invites name the listing and the candidate code only.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from . import contacts, fireflies, google_calendar, ics, interviews, mailer, meeting_notes, settings, whatsapp


def _summary(title: str, iid: int) -> str:
    return f"Interview: {title} ({interviews.tag(iid)})"


def _where(iv: dict) -> str:
    if iv["mode"] == "meet":
        return iv["meet_link"] or "The Google Meet link will be shared before the interview."
    if iv["mode"] == "phone":
        return "By phone. The NGO will connect you."
    return iv["location"] or "In person"


def _ics_people(iv: dict, employer_emails: list[str]) -> list[tuple[str, str]]:
    people = [(e, "employer") for e in employer_emails]
    if iv["interviewer_email"]:
        people.append((iv["interviewer_email"], "interviewer"))
    if iv["student_invited"] and contacts.email(iv["student_id"]):
        people.append((contacts.email(iv["student_id"]), "student"))  # type: ignore[arg-type]
    seen, out = set(), []
    for addr, who in people:
        if addr.lower() not in seen:
            seen.add(addr.lower())
            out.append((addr, who))
    return out


def _send_ics(iv: dict, title: str, employer_emails: list[str], cancelled: bool = False) -> int:
    start = datetime.fromisoformat(iv["starts_at"])
    data = ics.event(f"interview-{iv['id']}@opportunity-matcher", start, iv["minutes"], _summary(title, iv["id"]),
                     description=f"Candidate {iv.get('candidate_code', '')}".strip(), location=_where(iv),
                     sequence=iv["sequence"], cancelled=cancelled)
    when = interviews.words(iv["starts_at"])
    n = 0
    for addr, who in _ics_people(iv, employer_emails):
        subject, body = mailer.interview_invite(title, when, iv["minutes"], _where(iv),
                                                "This interview was cancelled." if cancelled else
                                                ("The NGO arranged this interview for you." if who == "student" else
                                                 f"Candidate code: {iv.get('candidate_code', '')}."))
        if cancelled:
            subject = "Cancelled: " + subject
        recipient = f"student:{iv['student_id']}" if who == "student" else f"{who}:{addr}"
        mailer.send(addr, subject, body, kind="interview", recipient=recipient,
                    attachments=[("interview.ics", "text/calendar", data)])
        n += 1
    return n


def schedule(application: dict, title: str, candidate_code: str, by: str, *, starts_at: str, minutes: int, interviewer: str,
             interviewer_email: str | None, mode: str, location: str | None, meet_link: str | None, notetaker: bool,
             invite_student: bool, employer_emails: list[str]) -> dict:
    """Save the interview and send the invites. Returns {"interview", "calendar", "warnings"}."""
    iv = interviews.create(application, starts_at, minutes, interviewer, by, interviewer_email=interviewer_email, mode=mode,
                           location=location, meet_link=meet_link, notetaker=notetaker)
    iv = interviews.update(iv["id"], student_invited=int(invite_student))
    iv["candidate_code"] = candidate_code
    warnings: list[str] = []
    calendar = "ics"
    ff = settings.fireflies()
    if notetaker and ff is None:
        warnings.append("Fireflies is not set up, so no notetaker was invited. Paste the notes after the call instead.")
    if google_calendar.connected() and mode != "phone":
        attendees = [e for e in employer_emails] + ([interviewer_email] if interviewer_email else [])
        if invite_student and contacts.email(application["student_id"]):
            attendees.append(contacts.email(application["student_id"]))  # type: ignore[arg-type]
        if notetaker and ff and mode == "meet":
            attendees.append(ff["bot_email"])
        try:
            ev = google_calendar.create_event(_summary(title, iv["id"]), f"Candidate {candidate_code}.", interviews.parse_when(iv["starts_at"]),
                                              minutes, attendees, location=location if mode == "in_person" else None,
                                              with_meet=mode == "meet" and not meet_link)
            iv = interviews.update(iv["id"], calendar="google", calendar_event_id=ev["id"], meet_link=meet_link or ev["meet_link"])
            calendar = "google"
        except google_calendar.GoogleError as e:
            warnings.append(f"Google Calendar did not take it ({e}). Invites went out by email instead.")
    if calendar == "ics":
        if mode == "meet" and not iv["meet_link"]:
            warnings.append("There is no meeting link yet. Add one, or connect Google in Settings to make Meet links.")
        iv = interviews.update(iv["id"], calendar="ics")
        iv["candidate_code"] = candidate_code
        if _send_ics(iv, title, employer_emails) == 0:
            warnings.append("Nobody had an email address, so no invite was sent. Add emails to the accounts in Settings.")
    tell_student(iv, title)
    return {"interview": interviews.get(iv["id"]), "calendar": calendar, "warnings": warnings}


def tell_student(iv: dict, title: str) -> int | None:
    link = iv["meet_link"] if iv["mode"] == "meet" and iv["meet_link"] else ("the NGO will call you" if iv["mode"] == "phone" else (iv["location"] or ""))
    when = interviews.words(iv["starts_at"])
    return whatsapp.send_template(iv["student_id"], "interview", [title, when, link],
                                  f"Your interview for {title} is on {when}. Join: {link}")


def reschedule(iv: dict, title: str, starts_at: str, minutes: int, employer_emails: list[str], candidate_code: str) -> dict:
    """Google is asked first, so if it refuses the interview keeps its old time and nobody is told of a move."""
    when = interviews.parse_when(starts_at)
    if when < datetime.now(when.tzinfo) - timedelta(minutes=5):
        raise interviews.InterviewError("That time has already passed.")
    google = iv["calendar"] == "google" and iv["calendar_event_id"]
    if google:
        google_calendar.move_event(iv["calendar_event_id"], datetime.fromisoformat(when.isoformat(timespec="minutes")), minutes)
    iv = interviews.update(iv["id"], starts_at=starts_at, minutes=minutes, sequence=iv["sequence"] + 1, status="scheduled")
    if not google:
        _send_ics({**iv, "candidate_code": candidate_code}, title, employer_emails)
    tell_student(iv, title)
    return iv


def cancel(iv: dict, title: str, employer_emails: list[str], candidate_code: str) -> dict:
    if iv["calendar"] == "google" and iv["calendar_event_id"]:
        google_calendar.cancel_event(iv["calendar_event_id"])
    elif iv["status"] == "scheduled":
        _send_ics({**iv, "sequence": iv["sequence"] + 1, "candidate_code": candidate_code}, title, employer_emails, cancelled=True)
    return interviews.update(iv["id"], status="cancelled", sequence=iv["sequence"] + 1)


# ---- notes ----

def send_notetaker_now(iv: dict, title: str) -> bool:
    if not iv["meet_link"]:
        raise fireflies.FirefliesError("This interview has no meeting link for the notetaker to join.")
    return fireflies.add_to_live(iv["meet_link"], _summary(title, iv["id"]), iv["minutes"])


def _store_notes(iv: dict, t: dict, known_names: list[str]) -> dict:
    from .privacy import redact
    summary, items = fireflies.notes_from(t)
    return interviews.set_notes(iv["id"], redact(summary, known_names), [redact(a, known_names) for a in items], "fireflies", t.get("id"))


def save_transcript(t: dict, known_names: list[str]) -> dict | None:
    """A Fireflies transcript: find its interview and store the summary and action points. None when it is not ours.
    The tag in the title comes first, because one Meet link can belong to several interviews."""
    iv = interviews.find_by_tag(t.get("title") or "") or interviews.find_by_link(t.get("meeting_link") or "")
    return _store_notes(iv, t, known_names) if iv else None


def fetch_notes(iv: dict, known_names: list[str]) -> dict | None:
    """Staff asked for this interview's notes, so they are saved on this interview."""
    t = fireflies.find(iv["meet_link"], interviews.tag(iv["id"]), iv["starts_at"][:10] + "T00:00:00.000Z")
    return _store_notes(iv, t, known_names) if t else None


def paste_notes(iv: dict, text: str, known_names: list[str]) -> dict:
    res = meeting_notes.extract(text, known_names)
    return interviews.set_notes(iv["id"], res["summary"], res["action_items"], f"pasted ({res['method']})")
