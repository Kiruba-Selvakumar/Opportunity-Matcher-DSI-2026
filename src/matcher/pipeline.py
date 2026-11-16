"""Run the whole pipeline: python -m matcher.pipeline [--from STEP] [--no-llm]."""
from __future__ import annotations

import argparse
import os
import time

STEPS = ["data", "clean", "vectors", "score", "rank", "explain"]


def _data() -> str:
    from .config import PATHS
    from .generate_opportunities import generate_opportunities
    from .generate_students import generate_students, holds_real_data
    if holds_real_data():
        return "kept your data in data/raw (it is not the sample data)"
    PATHS["students_raw"].parent.mkdir(parents=True, exist_ok=True)
    s, o = generate_students(), generate_opportunities()
    s.to_csv(PATHS["students_raw"], index=False, lineterminator="\n")
    o.to_csv(PATHS["opportunities_raw"], index=False, lineterminator="\n")
    return f"{len(s)} students, {len(o)} opportunities"


def _clean() -> str:
    from .clean import clean_all
    r = clean_all()
    return f"{r['students']['records']} students, {r['opportunities']['records']} opportunities"


def _vectors() -> str:
    from .embed import build_all, get_encoder
    norm = build_all()
    return f"{len(norm['students']) + len(norm['opportunities'])} profiles ({get_encoder().method})"


def _score() -> str:
    from .score import score_all
    rows = score_all()
    return f"{len(rows)} pairs, {sum(r.eligible for r in rows)} eligible"


def _rank() -> str:
    from .rank import rank_all
    return f"{len(rank_all())} students ranked"


def _explain() -> str:
    from .explain import explain_all
    return f"{len(explain_all())} students explained"


FUNCS = {"data": _data, "clean": _clean, "vectors": _vectors, "score": _score, "rank": _rank, "explain": _explain}


def run(from_step: str = "data", no_llm: bool = False, quiet: bool = False) -> dict[str, float]:
    if no_llm:
        os.environ["LLM_PROVIDER"] = "none"
    timings: dict[str, float] = {}
    for step in STEPS[STEPS.index(from_step):]:
        t = time.perf_counter()
        info = FUNCS[step]()
        timings[step] = time.perf_counter() - t
        if not quiet:
            print(f"[{step:<7}] {timings[step]:6.2f}s  {info}")
    return timings


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="from_step", default="data", choices=STEPS)
    ap.add_argument("--no-llm", action="store_true")
    a = ap.parse_args()
    run(a.from_step, a.no_llm)


if __name__ == "__main__":
    main()
