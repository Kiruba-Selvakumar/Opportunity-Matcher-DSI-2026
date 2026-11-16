"""Stored resume PDFs: one per student, kept in data/private/resumes and nowhere else.

Only NGO accounts and the student can open a resume. Employers never get the file (it carries the student's name), they
see the anonymous profile. The database keeps the ATS report, which holds no personal details. The text is read from the
PDF when needed and cached in memory, never written to disk.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from collections import OrderedDict
from pathlib import Path

from . import ats, auth, resume_pdf
from .config import PATHS
from .store import connect

SOURCES = ("student", "ngo", "bulk")
SAFE_ID = re.compile(r"^[A-Za-z0-9_-]{1,20}$")
ID_IN_NAME = re.compile(r"(?<![A-Za-z0-9])(S\d{3,4})(?!\d)", re.I)
CODE_IN_NAME = re.compile(r"(?<![0-9a-f])([0-9a-f]{8})(?![0-9a-f])")
NOISE = {"resume", "cv", "final", "updated", "new", "latest", "pdf", "copy", "my", "the", "of", "and", "v1", "v2"}
_text_cache: OrderedDict[tuple[str, str], str] = OrderedDict()


def file_for(student_id: str) -> Path:
    if not SAFE_ID.match(student_id):
        raise ValueError("bad student id")
    return Path(PATHS["resumes"]) / f"{student_id}.pdf"


def save(student_id: str, data: bytes, source: str, by: str, path: Path | str | None = None) -> dict:
    """Check, store and score a resume. Raises resume_pdf.ResumeError with a plain message when it cannot be used."""
    if source not in SOURCES:
        raise ValueError("unknown source")
    text, pages = resume_pdf.pdf_to_text(data)
    report = ats.quality(text, pages)
    target = file_for(student_id)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, target)                     # atomic: a reader never sees half a file
    sha = hashlib.sha256(data).hexdigest()
    c = connect(path)
    try:
        c.execute("INSERT INTO resumes (student_id, sha256, bytes, pages, source, uploaded_by, uploaded_at, quality, report) "
                  "VALUES (?,?,?,?,?,?,?,?,?) ON CONFLICT(student_id) DO UPDATE SET sha256 = excluded.sha256, bytes = excluded.bytes, "
                  "pages = excluded.pages, source = excluded.source, uploaded_by = excluded.uploaded_by, "
                  "uploaded_at = excluded.uploaded_at, quality = excluded.quality, report = excluded.report",
                  (student_id, sha, len(data), pages, source, by, auth.iso(auth.now()), report["score"], json.dumps(report)))
    finally:
        c.close()
    _remember(student_id, sha, text)
    return meta(student_id, path)  # type: ignore[return-value]


def _row(r) -> dict:
    d = dict(r)
    d["report"] = json.loads(d["report"]) if d.get("report") else None
    return d


def meta(student_id: str, path: Path | str | None = None) -> dict | None:
    c = connect(path)
    try:
        r = c.execute("SELECT * FROM resumes WHERE student_id = ?", (student_id,)).fetchone()
        return _row(r) if r else None
    finally:
        c.close()


def all_meta(path: Path | str | None = None) -> dict[str, dict]:
    c = connect(path)
    try:
        return {r["student_id"]: _row(r) for r in c.execute("SELECT * FROM resumes")}
    finally:
        c.close()


def delete(student_id: str, path: Path | str | None = None) -> bool:
    f = file_for(student_id)
    if f.exists():
        f.unlink()
    c = connect(path)
    try:
        return c.execute("DELETE FROM resumes WHERE student_id = ?", (student_id,)).rowcount > 0
    finally:
        c.close()


def _remember(student_id: str, sha: str, text: str) -> None:
    _text_cache[(student_id, sha)] = text
    _text_cache.move_to_end((student_id, sha))
    while len(_text_cache) > 256:
        _text_cache.popitem(last=False)


def text(student_id: str, path: Path | str | None = None) -> str | None:
    """The resume's text, read from the PDF when it is not cached. None when there is no resume."""
    m = meta(student_id, path)
    f = file_for(student_id)
    if m is None or not f.exists():
        return None
    key = (student_id, m["sha256"])
    if key not in _text_cache:
        try:
            _remember(student_id, m["sha256"], resume_pdf.pdf_to_text(f.read_bytes())[0])
        except resume_pdf.ResumeError:
            return None
    return _text_cache[key]


# ---- bulk upload: which file belongs to which student ----

def _tokens(s: str) -> list[str]:
    return [t for t in re.split(r"[^a-z]+", s.lower()) if len(t) >= 3 and t not in NOISE]


def match_filenames(filenames: list[str], student_ids: list[str], codes: dict[str, str], names: dict[str, str]) -> list[dict]:
    """For each file: the student it belongs to and how we know. A student ID or candidate code in the name is certain.
    A name match is only a suggestion that staff confirm, and two students with the same name give no suggestion."""
    ids = {s.upper(): s for s in student_ids}
    name_tokens = {sid: set(_tokens(n)) for sid, n in names.items() if n}
    out = []
    for fn in filenames:
        stem = re.sub(r"\.pdf$", "", fn, flags=re.I)
        m = ID_IN_NAME.search(stem)
        if m and m.group(1).upper() in ids:
            out.append({"file": fn, "student_id": ids[m.group(1).upper()], "how": "id"})
            continue
        m = CODE_IN_NAME.search(stem.lower())
        if m and m.group(1) in codes:
            out.append({"file": fn, "student_id": codes[m.group(1)], "how": "code"})
            continue
        have = set(_tokens(stem))
        hits = [sid for sid, toks in name_tokens.items() if toks and toks <= have]
        if len(hits) == 1:
            out.append({"file": fn, "student_id": hits[0], "how": "name"})
        else:
            out.append({"file": fn, "student_id": None, "how": "ambiguous" if hits else None, "options": sorted(hits)[:5]})
    return out
