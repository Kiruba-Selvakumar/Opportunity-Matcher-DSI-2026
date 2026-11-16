"""Keep names, phones and emails out of logs, LLM calls and clean files."""
from __future__ import annotations

import re

import pandas as pd

PHONE_RE = re.compile(r"(?<![\w+])(?:\+91[\s-]?)?(?<!\d)[6-9]\d{9}(?!\d)")
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
PII_COLUMNS = ["name", "phone", "email"]


class PIIError(ValueError):
    """Raised when personal details are found where they must not be."""


def split_contacts(df_raw: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return (contacts, df_without_pii)."""
    contacts = df_raw[["student_id", *PII_COLUMNS]].copy()
    rest = df_raw.drop(columns=PII_COLUMNS)
    return contacts, rest


def _name_tokens(known_names: list[str]) -> list[str]:
    tokens = set()
    for name in known_names or []:
        for part in re.split(r"\s+", str(name).strip()):
            if len(part) >= 3:
                tokens.add(part)
    return sorted(tokens, key=len, reverse=True)


def _name_pattern(known_names: list[str]) -> re.Pattern | None:
    tokens = _name_tokens(known_names)
    if not tokens:
        return None
    return re.compile(r"\b(?:" + "|".join(re.escape(t) for t in tokens) + r")\b", re.IGNORECASE)


def redact(text: str, known_names: list[str]) -> str:
    """Remove phones, emails and known names."""
    if not text:
        return text
    out = EMAIL_RE.sub("[email]", text)
    out = PHONE_RE.sub("[phone]", out)
    pat = _name_pattern(known_names)
    if pat:
        out = pat.sub("[name]", out)
    return out


def assert_no_pii(payload: str, known_names: list[str]) -> None:
    if PHONE_RE.search(payload):
        raise PIIError("phone number found in payload")
    if EMAIL_RE.search(payload):
        raise PIIError("email found in payload")
    pat = _name_pattern(known_names)
    if pat and pat.search(payload):
        raise PIIError("a known name was found in payload")


def candidate_code(student_id: str, salt: str) -> str:
    """A short code employers see instead of a student ID. Staff can search by it."""
    import hashlib
    return hashlib.sha256(f"{salt}{student_id}".encode()).hexdigest()[:8]
