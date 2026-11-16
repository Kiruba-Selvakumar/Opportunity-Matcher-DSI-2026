"""Matching v2 inputs: skill weights, related skills, branch fit, past decisions and how busy each listing is."""
from __future__ import annotations

import csv
import math
from dataclasses import dataclass, field
from functools import lru_cache

from . import config
from .config import PATHS
from .schema import Decision, Opportunity

STATE = {"Warangal": "TS", "Khammam": "TS", "Karimnagar": "TS", "Nizamabad": "TS", "Nalgonda": "TS", "Mahabubnagar": "TS",
         "Hyderabad": "TS", "Guntur": "AP", "Vijayawada": "AP", "Tirupati": "AP", "Visakhapatnam": "AP",
         "Bengaluru": "KA", "Chennai": "TN", "Pune": "MH"}


@lru_cache(maxsize=1)
def load_related() -> dict[tuple[str, str], float]:
    """(skill the student has, skill the listing needs) -> credit between 0 and 1."""
    with open(PATHS["related_skills"], newline="") as f:
        return {(r["have"], r["need"]): float(r["credit"]) for r in csv.DictReader(f)}


@lru_cache(maxsize=1)
def load_branch_fit() -> dict[tuple[str, str], float]:
    with open(PATHS["branch_fit"], newline="") as f:
        return {(r["branch"], r["job_family"]): min(float(r["bonus"]), config.BRANCH_FIT_MAX) for r in csv.DictReader(f)}


@dataclass
class Context:
    idf: dict[str, float] = field(default_factory=dict)
    max_idf: float = 1.0
    related: dict[tuple[str, str], float] = field(default_factory=dict)
    categories: dict[str, str] = field(default_factory=dict)
    branch_fit: dict[tuple[str, str], float] = field(default_factory=dict)
    prior: dict[str, tuple[int, int]] = field(default_factory=dict)     # job family -> (accepts, decisions)
    load: dict[str, int] = field(default_factory=dict)                   # listing -> students in play
    flags: dict[str, bool] = field(default_factory=lambda: dict(config.V2))
    v3: dict[str, bool] = field(default_factory=lambda: dict(config.V3))
    model: object | None = None                                          # learn.Model once there are enough outcomes
    competition: dict[str, list[float]] | None = None                    # listing -> eligible students' scores (relative.py)

    @classmethod
    def build(cls, opps: list[Opportunity], norm: dict, decisions: list[Decision] | None = None,
              load: dict[str, int] | None = None, flags: dict[str, bool] | None = None) -> "Context":
        from .skills import load_categories
        n = len(opps)
        df: dict[str, int] = {}
        for o in opps:
            for s in set(norm["opportunities"][o.opp_id]["skills"]):
                df[s] = df.get(s, 0) + 1
        idf = {s: math.log((n + 1) / (c + 1)) + 1 for s, c in df.items()}
        by_id = {o.opp_id: o for o in opps}
        prior: dict[str, tuple[int, int]] = {}
        for d in decisions or []:
            o = by_id.get(d.opp_id)
            if o is None or d.decision == "flag" or d.what_if:
                continue
            a, t = prior.get(o.job_family, (0, 0))
            prior[o.job_family] = (a + (d.decision == "accept"), t + 1)
        return cls(idf=idf, max_idf=math.log(n + 1) + 1, related=load_related(), categories=load_categories(),
                   branch_fit=load_branch_fit(), prior=prior, load=dict(load or {}),
                   flags=dict(flags if flags is not None else config.V2))

    @classmethod
    def v1(cls, opps: list[Opportunity], norm: dict) -> "Context":
        ctx = cls.build(opps, norm, flags={k: False for k in config.V2})
        ctx.v3 = {k: False for k in config.V3}
        return ctx

    def weight(self, skill: str, nice: bool) -> float:
        w = self.idf.get(skill, self.max_idf) if self.flags.get("idf") else 1.0
        return w * (config.NICE_WEIGHT if nice else 1.0)

    def credit(self, have: list[str], need: str) -> tuple[float, str | None]:
        """How much the student's skills count toward one needed skill, and which of theirs gave the credit."""
        if need in have:
            return 1.0, need
        if not self.flags.get("related"):
            return 0.0, None
        best, who = 0.0, None
        for h in have:
            c = self.related.get((h, need))
            if c is None and self.categories.get(h) and self.categories.get(h) == self.categories.get(need):
                c = config.SAME_CATEGORY_CREDIT
            if c is not None and c > best:
                best, who = c, h
        return best, who


def prior_adjustment(ctx: Context, job_family: str) -> tuple[float, str | None]:
    if not ctx.flags.get("prior"):
        return 0.0, None
    accepts, total = ctx.prior.get(job_family, (0, 0))
    if total < config.PRIOR_MIN_DECISIONS:
        return 0.0, None
    p = (accepts + 2) / (total + 4)
    adj = max(-config.PRIOR_MAX, min(config.PRIOR_MAX, (p - 0.5) * 2 * config.PRIOR_MAX))
    return round(adj, 4), f"Staff accepted {accepts} of {total} similar matches"


def congestion_penalty(ctx: Context, opp: Opportunity) -> float:
    if not ctx.flags.get("congestion"):
        return 0.0
    limit = config.CONGESTION_FACTOR * max(1, opp.openings)
    load = ctx.load.get(opp.opp_id, 0)
    if load <= limit:
        return 0.0
    return round(min(config.CONGESTION_MAX, config.CONGESTION_MAX * (load - limit) / limit), 4)
