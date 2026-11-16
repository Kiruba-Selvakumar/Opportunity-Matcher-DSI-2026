"""Skill list, synonyms and the normalizer."""
from __future__ import annotations

import csv
import difflib
import re
from functools import lru_cache

import numpy as np

from .config import EMBED_MATCH_CUTOFF, FUZZY_CUTOFF, PATHS
from .schema import Opportunity, Student


@lru_cache(maxsize=1)
def _vocab_rows() -> tuple[tuple[str, str, str, str], ...]:
    with open(PATHS["skills_vocab"], newline="") as f:
        return tuple((r["skill_id"], r["skill"], r["category"], r["source"]) for r in csv.DictReader(f))


def load_vocab() -> list[str]:
    return [r[1] for r in _vocab_rows()]


def load_categories() -> dict[str, str]:
    return {r[1]: r[2] for r in _vocab_rows()}


@lru_cache(maxsize=1)
def _synonyms() -> dict[str, tuple[str, ...]]:
    out: dict[str, list[str]] = {}
    with open(PATHS["synonyms"], newline="") as f:
        for r in csv.DictReader(f):
            out.setdefault(r["alias"].strip().lower(), []).append(r["canonical"].strip())
    return {k: tuple(v) for k, v in out.items()}


def load_synonyms() -> dict[str, list[str]]:
    return {k: list(v) for k, v in _synonyms().items()}


def _clean_phrase(p: str) -> str:
    p = p.lower().strip()
    p = re.sub(r"\s+", " ", p)
    return p.strip(" .,;:-_()[]{}\"'")


_emb_cache: dict[int, np.ndarray] = {}


def _embed_match(phrase: str, enc, vocab: list[str]) -> str | None:
    # Character TF-IDF similarity is too loose to trust at this cutoff, so only real embeddings are used here.
    if enc is None or getattr(enc, "method", "") != "minilm":
        return None
    key = id(enc)
    if key not in _emb_cache:
        _emb_cache[key] = enc.encode(vocab)
    sims = _emb_cache[key] @ enc.encode([phrase])[0]
    i = int(np.argmax(sims))
    return vocab[i] if sims[i] >= EMBED_MATCH_CUTOFF else None


def normalize(phrases: list[str], encoder=None) -> tuple[list[str], list[str]]:
    """Return (canonical_skills, unmatched). Order is kept, duplicates removed."""
    vocab = load_vocab()
    lower = {s.lower(): s for s in vocab}
    syn = _synonyms()
    found: list[str] = []
    unmatched: list[str] = []

    def add(items):
        for it in items:
            if it not in found:
                found.append(it)

    for raw in phrases:
        p = _clean_phrase(raw)
        if not p:
            continue
        if p in lower:
            add([lower[p]])
        elif p in syn:
            add(syn[p])
        else:
            close = difflib.get_close_matches(p, list(lower), n=1, cutoff=FUZZY_CUTOFF)
            if close:
                add([lower[close[0]]])
                continue
            emb = _embed_match(p, encoder, vocab)
            if emb:
                add([emb])
            elif p not in unmatched:
                unmatched.append(p)
    return found, unmatched


def implied_skills(student: Student) -> list[str]:
    out = []
    if "Telugu" in student.languages:
        out.append("Telugu Communication")
    if "Hindi" in student.languages:
        out.append("Hindi Communication")
    if "English" in student.languages and student.english_level in ("intermediate", "fluent"):
        out.append("English Communication")
    return out


def normalize_student(student: Student, encoder=None) -> dict:
    skills, unmatched = normalize(student.skills_raw, encoder)
    for s in implied_skills(student):
        if s not in skills:
            skills.append(s)
    return {"skills": skills, "unmatched": unmatched}


def normalize_opportunity(opp: Opportunity, encoder=None) -> dict:
    skills, unmatched = normalize(opp.required_skills_raw, encoder)
    nice, _ = normalize(opp.nice_to_have, encoder)
    return {"skills": skills, "unmatched": unmatched, "nice": [n for n in nice if n in skills]}


NON_TECHNICAL = {"soft", "local"}


def technical(skills: list[str]) -> list[str]:
    """Skills that say what someone can do, without soft skills and certificates.

    Soft skills such as "English Communication" are shared by almost every profile, so they make unrelated profiles look
    similar. They still count in coverage. They are left out only of the similarity between two skill profiles.
    """
    cats = load_categories()
    return [s for s in skills if cats.get(s) not in NON_TECHNICAL]
