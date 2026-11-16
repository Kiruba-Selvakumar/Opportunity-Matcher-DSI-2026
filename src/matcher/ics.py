"""Calendar files (.ics) for interviews, for when Google Calendar is not connected. Any calendar app opens them."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone


def _esc(s: str) -> str:
    return s.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def _utc(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def event(uid: str, start: datetime, minutes: int, summary: str, description: str = "", location: str = "",
          sequence: int = 0, cancelled: bool = False) -> bytes:
    """One event. Send it again with the same uid and a higher sequence to move it; cancelled=True removes it."""
    lines = [
        "BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Opportunity Matcher//Interviews//EN",
        f"METHOD:{'CANCEL' if cancelled else 'REQUEST'}", "BEGIN:VEVENT",
        f"UID:{uid}", f"SEQUENCE:{sequence}", f"DTSTAMP:{_utc(datetime.now(timezone.utc))}",
        f"DTSTART:{_utc(start)}", f"DTEND:{_utc(start + timedelta(minutes=minutes))}",
        f"SUMMARY:{_esc(summary)}", f"DESCRIPTION:{_esc(description)}", f"LOCATION:{_esc(location)}",
        f"STATUS:{'CANCELLED' if cancelled else 'CONFIRMED'}", "END:VEVENT", "END:VCALENDAR",
    ]
    return ("\r\n".join(lines) + "\r\n").encode()
