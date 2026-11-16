"""Email through any SMTP server. Without SMTP_HOST every email is a dry run in the outbox.

Emails go to employers and NGO staff (their account email) and, for an interview, to the student's private email when
staff ask for it. Bodies hold listing titles and links only: never a student's name, phone or ID.
"""
from __future__ import annotations

import smtplib
import ssl
from email.message import EmailMessage

from . import outbox, settings, standins

Attachment = tuple[str, str, bytes]   # (filename, mime type, content)


def send(to: str, subject: str, body: str, *, kind: str, recipient: str, attachments: list[Attachment] | None = None,
         batch_id: str | None = None) -> int:
    """Queue one email and return its outbox id. Student addresses are stored masked."""
    cfg = settings.smtp()
    is_student = recipient.startswith("student:")
    shown, why_held = outbox.mask(to) if is_student else to, None
    if standins.active():
        route = standins.email_route(to, recipient.removeprefix("student:") if is_student else None)
        if route:
            shown, to, subject = f"{shown} via {outbox.mask(route[0])}", route[0], f"[TEST for {route[1]}] {subject}"
        else:
            why_held = standins.HELD
    oid = outbox.add("email", kind, recipient, shown, body, subject=subject, status="queued" if cfg and not why_held else "dry_run", batch_id=batch_id)
    if why_held:
        outbox.mark(oid, "dry_run", error=why_held)
    elif cfg:
        outbox.run(lambda: _deliver(oid, cfg, to, subject, body, attachments or []))
    return oid


def _deliver(oid: int, cfg: dict, to: str, subject: str, body: str, attachments: list[Attachment]) -> None:
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = cfg["from"], to, subject
    msg.set_content(body)
    for name, mime, data in attachments:
        main, sub = mime.split("/", 1)
        msg.add_attachment(data, maintype=main, subtype=sub, filename=name)
    try:
        if cfg["ssl"]:
            with smtplib.SMTP_SSL(cfg["host"], cfg["port"], context=ssl.create_default_context(), timeout=20) as s:
                _login_and_send(s, cfg, msg)
        else:
            with smtplib.SMTP(cfg["host"], cfg["port"], timeout=20) as s:
                s.starttls(context=ssl.create_default_context())
                _login_and_send(s, cfg, msg)
        outbox.mark(oid, "sent")
    except Exception as e:  # noqa: BLE001 - any failure is recorded on the row, never raised into a request
        outbox.mark(oid, "failed", error=f"{type(e).__name__}: {e}")


def _login_and_send(s: smtplib.SMTP, cfg: dict, msg: EmailMessage) -> None:
    if cfg["user"]:
        s.login(cfg["user"], cfg["password"])
    s.send_message(msg)


# ---- the texts ----

def listing_reviewed(title: str, approved: bool, note: str | None, oid: str) -> tuple[str, str]:
    link = f"{settings.app_url()}/employer/{oid}"
    if approved:
        return (f"Your listing \"{title}\" is live",
                f"Good news. The NGO reviewed \"{title}\" and it is now live, so matching students can see it.\n\n"
                + (f"Note from the reviewer: {note}\n\n" if note else "") + f"Open it here: {link}\n")
    return (f"Your listing \"{title}\" needs a change",
            f"The NGO reviewed \"{title}\" and did not approve it yet.\n\nWhat to change: {note or 'see the note in the app'}\n\n"
            f"Edit and send it again here: {link}\n")


def candidate_shared(title: str, oid: str) -> tuple[str, str]:
    return (f"A candidate was shared for \"{title}\"",
            f"The NGO shared a candidate with you for \"{title}\". You can see their skills and move them along "
            f"(shortlist, interview, offer) here: {settings.app_url()}/employer/{oid}\n")


def interview_invite(title: str, when: str, minutes: int, where: str, for_whom: str) -> tuple[str, str]:
    return (f"Interview: {title}, {when}",
            f"An interview for \"{title}\" is set for {when} ({minutes} minutes).\n\nWhere: {where}\n\n"
            f"{for_whom}\nA calendar file is attached.\n")


def new_message(link: str, about: str | None = None) -> tuple[str, str]:
    """An alert that the NGO wrote. It never repeats the message, so nothing private sits in an inbox or the outbox."""
    what = f" about \"{about}\"" if about else ""
    return ("You have a new message from the NGO",
            f"The NGO sent you a message{what}. Open it here: {link}\n\n"
            "You will not get another email for new messages until you have read this one.\n")
