"""Pick the top 5 per student. Writes top5.json (reasons are filled in by explain.py)."""
from __future__ import annotations

import json
from collections import Counter

from .config import PATHS, TOP_K
from .embed import get_encoder
from .schema import MatchRow, TopMatch
from .score import load_clean, opp_vectors, score_student

MAX_PER_TYPE = 3


def _sort_key(r: MatchRow):
    return (-r.final_score, r.unknown_count(), -(r.pay_max or 0), r.opp_id)


def top_k(rows: list[MatchRow], k: int = TOP_K, min_score: float = 0.0) -> list[MatchRow]:
    """The best eligible matches, at most 3 of one type. Anything below min_score is left out."""
    out: list[MatchRow] = []
    per_type: Counter = Counter()
    for r in sorted((r for r in rows if r.eligible and r.final_score >= min_score), key=_sort_key):
        if per_type[r.type] >= MAX_PER_TYPE:
            continue
        out.append(r)
        per_type[r.type] += 1
        if len(out) == k:
            break
    return out


def to_top_matches(rows: list[MatchRow]) -> list[TopMatch]:
    res = []
    for i, r in enumerate(rows, start=1):
        warnings = [f"{name}: {c.note}" for name, c in r.checks.items() if c.status == "unknown"]
        res.append(TopMatch(rank=i, opp_id=r.opp_id, title=r.title, org_name=r.org_name, type=r.type, city=r.city,
                            mode=r.mode, final_score=r.final_score, overlap=r.overlap, missing=r.missing,
                            checks=r.checks, warnings=warnings, reason="", reason_method="template",
                            related=r.related, crowded=r.crowded, prior_note=r.prior_note, teaches=r.teaches,
                            upskill=r.upskill, standing=r.standing, ml=r.ml))
    return res


def rank_all() -> dict[str, list[dict]]:
    students, opps, norm = load_clean()
    enc = get_encoder()
    ov = opp_vectors(opps, norm, enc)
    out = {}
    for s in students:
        picks = top_k(score_student(s, opps, norm, enc, ov))
        out[s.student_id] = [m.model_dump() for m in to_top_matches(picks)]
    PATHS["top5"].parent.mkdir(parents=True, exist_ok=True)
    PATHS["top5"].write_text(json.dumps(out, indent=1))
    return out


def main() -> None:
    out = rank_all()
    print(f"ranked {len(out)} students")


if __name__ == "__main__":
    main()
