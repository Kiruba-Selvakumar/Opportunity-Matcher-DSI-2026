"""Action points from a pasted meeting transcript (from Google Meet, Otter, Fireflies or typed notes).

Names, phones and emails are removed first. With an LLM set up, it writes the summary and the action points; without one
(or if it returns something unusable), lines that read like a task are kept.
"""
from __future__ import annotations

import re

from . import llm
from .privacy import PIIError, redact

MAX_CHARS = 30000
SYSTEM = ("You read an interview or meeting transcript for a placement NGO. Return JSON with keys "
          '"summary" (two or three plain sentences) and "action_items" (a list of short tasks, each starting with a verb, '
          "saying who should do it if the transcript says so). Use only what the transcript says.")
TASK = re.compile(r"\b(will|shall|need(?:s)? to|has to|have to|should|must|follow up|action|next step|send|share|schedule|"
                  r"submit|call back|confirm|prepare|complete|by (?:monday|tuesday|wednesday|thursday|friday|tomorrow|next week))\b", re.I)


def _rules(text: str) -> list[str]:
    out: list[str] = []
    for part in re.split(r"(?<=[.!?])\s+|\n+", text):
        s = re.sub(r"^\s*(?:\[?\d{1,2}:\d{2}(?::\d{2})?\]?\s*)?(?:(?:[A-Z][\w .]{0,30}|\[name\](?: \[name\])*):\s*)?", "", part).strip()
        if 12 <= len(s) <= 220 and TASK.search(s) and s not in out:
            out.append(s)
    return out[:10]


def extract(text: str, known_names: list[str]) -> dict:
    """{"summary", "action_items", "method"} from transcript text."""
    clean = redact((text or "")[:MAX_CHARS], known_names)
    if not clean.strip():
        raise ValueError("Paste the transcript or the meeting notes first.")
    if llm.provider() != "none":
        try:
            res = llm.complete_json(SYSTEM, clean, {"summary": "str", "action_items": ["str"]}, known_names=known_names)
        except PIIError:
            res = None
        if res and isinstance(res.get("action_items"), list) and all(isinstance(a, str) for a in res["action_items"]):
            return {"summary": redact(str(res.get("summary") or ""), known_names)[:1500],
                    "action_items": [redact(a, known_names)[:300] for a in res["action_items"]][:15], "method": "llm"}
    return {"summary": "", "action_items": _rules(clean), "method": "rule"}
