"""Keyword baseline: Jaccard overlap of lowercase word tokens. No filters and no normalization."""
from __future__ import annotations

import re

import pandas as pd

from matcher.config import PATHS, TOP_K


def tokens(text) -> set[str]:
    return set(re.findall(r"\w+", str(text or "").lower()))


def jaccard(a: set[str], b: set[str]) -> float:
    return len(a & b) / len(a | b) if (a | b) else 0.0


def baseline_scores(students_raw: pd.DataFrame, opps_raw: pd.DataFrame) -> dict[str, list[tuple[str, float]]]:
    """For every student, all opportunities sorted best first (ties broken by opp_id)."""
    o_tok = {r.opp_id: tokens(r.required_skills_text) for r in opps_raw.itertuples()}
    out = {}
    for r in students_raw.itertuples():
        st = tokens(r.skills_text)
        scored = [(oid, jaccard(st, ot)) for oid, ot in o_tok.items()]
        out[r.student_id] = sorted(scored, key=lambda x: (-x[1], x[0]))
    return out


def baseline_top(students_raw: pd.DataFrame, opps_raw: pd.DataFrame, k: int = TOP_K) -> dict[str, list[str]]:
    return {sid: [o for o, _ in lst[:k]] for sid, lst in baseline_scores(students_raw, opps_raw).items()}


def load_raw() -> tuple[pd.DataFrame, pd.DataFrame]:
    return (pd.read_csv(PATHS["students_raw"], dtype=str, keep_default_na=False),
            pd.read_csv(PATHS["opportunities_raw"], dtype=str, keep_default_na=False))


if __name__ == "__main__":
    s, o = load_raw()
    for sid, top in list(baseline_top(s, o).items())[:3]:
        print(sid, top)
