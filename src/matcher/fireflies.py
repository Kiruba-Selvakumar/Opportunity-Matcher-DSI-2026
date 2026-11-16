"""Fireflies.ai notetaker: records interviews nobody from the NGO can join, and sends back a summary and action points.

How it joins: the Fireflies bot's email is added to the calendar invite (meetings.py), so it joins on its own. If it was
left out, "Send the notetaker now" asks it to join a live meeting (Fireflies allows about 3 of these per 20 minutes).
How notes come back: Fireflies calls our webhook when a transcript is ready, or staff press "Fetch notes". The transcript
is matched to the interview by the INT-<id> tag in the meeting title, or else by its Meet link.
"""
from __future__ import annotations

import hashlib
import hmac
import re

from . import settings

API = "https://api.fireflies.ai/graphql"
FIELDS = "id title date meeting_link transcript_url summary { overview action_items keywords }"


class FirefliesError(RuntimeError):
    """Fireflies refused or is not set up. The message is safe to show to staff."""


def _http(json_body: dict, key: str):
    """Every call to Fireflies goes through here, so tests can replace it."""
    import httpx
    return httpx.post(API, json=json_body, headers={"Authorization": f"Bearer {key}"}, timeout=30)


def _gql(query: str, variables: dict) -> dict:
    cfg = settings.fireflies()
    if cfg is None:
        raise FirefliesError("Fireflies is not set up. Add FIREFLIES_API_KEY to .env.")
    r = _http({"query": query, "variables": variables}, cfg["api_key"])
    data = r.json() if r.content else {}
    if r.status_code >= 400 or data.get("errors"):
        err = (data.get("errors") or [{}])[0]
        raise FirefliesError(err.get("message") or f"Fireflies said {r.status_code}.")
    return data.get("data") or {}


def add_to_live(meet_link: str, title: str, minutes: int = 60) -> bool:
    q = ("mutation Add($link: String!, $title: String, $duration: Int) "
         "{ addToLiveMeeting(meeting_link: $link, title: $title, duration: $duration) { success } }")
    d = _gql(q, {"link": meet_link, "title": title[:256], "duration": max(15, min(120, minutes))})
    return bool((d.get("addToLiveMeeting") or {}).get("success"))


def transcript(transcript_id: str) -> dict | None:
    return _gql(f"query T($id: String!) {{ transcript(id: $id) {{ {FIELDS} }} }}", {"id": transcript_id}).get("transcript")


def find(meet_link: str | None, tag: str, from_iso: str | None = None) -> dict | None:
    """The transcript of one interview: its exact tag in the title (INT-1 is not INT-12), or else the same Meet link
    on a transcript whose title names no other interview (a Meet room can be used for several interviews)."""
    q = (f"query F($keyword: String, $from: DateTime) {{ transcripts(keyword: $keyword, scope: \"title\", fromDate: $from, limit: 10) "
         f"{{ {FIELDS} }} }}")
    items = _gql(q, {"keyword": tag, "from": from_iso}).get("transcripts") or []
    exact = re.compile(rf"\b{re.escape(tag)}\b")
    for t in items:
        if exact.search(t.get("title") or ""):
            return t
    want = _link(meet_link)
    for t in items:
        if want and _link(t.get("meeting_link")) == want and not re.search(r"\bINT-\d+\b", t.get("title") or ""):
            return t
    return None


def _link(link: str | None) -> str:
    return re.sub(r"[?#].*$", "", (link or "").strip().lower()).rstrip("/")


def verify_signature(raw: bytes, header: str | None, secret: str) -> bool:
    """x-hub-signature: HMAC-SHA256 of the raw body with the webhook secret, as hex (a "sha256=" prefix is accepted)."""
    if not secret or not header:
        return False
    good = hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    return hmac.compare_digest(good, header.strip().removeprefix("sha256="))


def notes_from(t: dict) -> tuple[str, list[str]]:
    """(summary, action points) from a transcript. Speaker headings are dropped, so no names come along."""
    s = t.get("summary") or {}
    raw = s.get("action_items") or ""
    lines = raw if isinstance(raw, list) else str(raw).splitlines()
    items = []
    for line in lines:
        line = line.strip()
        if not line or (line.startswith("**") and line.endswith("**")) or line.endswith(":"):
            continue                                            # "**Speaker Name**" headings
        line = line.lstrip("-•*").strip()
        items.append(re.sub(r"\s*\(\d{1,2}:\d{2}(?::\d{2})?\)\s*$", "", line))
    return (s.get("overview") or "").strip(), items
