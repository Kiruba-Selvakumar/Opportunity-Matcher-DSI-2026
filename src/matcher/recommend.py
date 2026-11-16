"""Close the gap: training and mentors that teach what a match is missing. And the fit label students see."""
from __future__ import annotations

from . import config
from .schema import MatchRow


def close_the_gap(rows: list[MatchRow], norm: dict, missing: list[str], k: int = 2, exclude: str | None = None) -> list[dict]:
    """Up to k eligible training or mentor listings that cover the most of the missing skills. No repeats by title."""
    miss = set(missing)
    if not miss:
        return []
    found, titles = [], set()
    for r in rows:
        if r.type not in ("training", "mentor") or not r.eligible or r.opp_id == exclude:
            continue
        covers = [s for s in norm["opportunities"][r.opp_id]["skills"] if s in miss]
        if covers:
            found.append((-len(covers), -r.final_score, r.opp_id, r, covers))
    found.sort(key=lambda x: x[:3])
    found = [f for f in found if not (f[3].title in titles or titles.add(f[3].title))]
    return [{"opp_id": r.opp_id, "title": r.title, "type": r.type, "covers": covers, "cost": r.upfront_cost}
            for _, _, _, r, covers in found[:k]]


def fit_label(final: float, has_closer: bool) -> str:
    if final >= config.FIT_STRONG:
        return "Strong fit"
    if final >= config.FIT_GOOD:
        return "Good fit"
    return "Stretch" if has_closer else "Possible fit"
