"""ML scoring: learn from what actually happened to matches, and nudge similar matches up or down.

Labels come from people, never from the rule score: a staff accept or reject, and what happened after a student was put
forward (shortlisted, interviewed, offered or hired is a yes; "not a fit" from the employer or "declined" by the NGO is a
no). The later outcome wins over an earlier staff decision. A logistic regression learns which parts of a match (skill
fit, missing skills, cost, distance, hours) go with a yes. It waits for ML_MIN_LABELS labels with at least
ML_MIN_PER_CLASS of each kind, and its nudge grows with the number of labels up to ML_MAX. Staff see the learned chance
and the nudge in "How this score was made".
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from . import adjust, config
from .related import Context
from .schema import Decision, MatchRow

FEATURES = {  # name -> plain words for the Settings page
    "skill_sim": "skill profiles look alike", "coverage": "needed skills covered", "n_missing": "missing skills",
    "related": "related skills count partly", "unknown": "facts still unknown", "needs_move": "needs a move",
    "cost": "costs money up front", "long_hours": "long hours", "low_safety": "lower safety score",
    "is_job": "a job (not training)", "nudges": "the other small nudges",
}
YES = ("shortlisted", "interview", "offered", "hired")
NO = ("not_a_fit", "declined")


def features(r: MatchRow) -> list[float]:
    nudges = sum(v for k, v in r.adjustments.items() if k not in ("ml", "standing"))
    return [r.skill_sim, r.coverage, float(len(r.missing)), sum(x["credit"] for x in r.related), float(r.unknown_count()),
            1.0 if r.checks["location"].note.startswith("needs move") else 0.0, min(r.upfront_cost, 30000) / 10000,
            1.0 if r.penalty_hours else 0.0, r.penalty_safety * 10, 1.0 if r.type == "job" else 0.0, nudges * 10]


def labels(decisions: list[Decision], apps: list[dict]) -> dict[tuple[str, str], int]:
    out: dict[tuple[str, str], int] = {}
    for d in sorted(decisions, key=lambda d: d.created_at or ""):
        if d.what_if or d.decision == "flag":
            continue
        out[(d.student_id, d.opp_id)] = 1 if d.decision == "accept" else 0
    for a in apps:
        if a["status"] in YES:
            out[(a["student_id"], a["opp_id"])] = 1
        elif a["status"] in NO:
            out[(a["student_id"], a["opp_id"])] = 0
    return out


@dataclass
class Model:
    mean: np.ndarray
    scale: np.ndarray
    coef: np.ndarray
    intercept: float
    n: int
    positives: int

    def chance(self, r: MatchRow) -> float:
        x = (np.asarray(features(r)) - self.mean) / self.scale
        return float(1 / (1 + np.exp(-(x @ self.coef + self.intercept))))

    @property
    def weight(self) -> float:
        return min(1.0, self.n / config.ML_FULL_WEIGHT_AT)


def train(by_student: dict[str, list[MatchRow]], labelled: dict[tuple[str, str], int]) -> Model | None:
    """A model, or None while there are too few labels of either kind."""
    X, y = [], []
    for (sid, oid), lab in sorted(labelled.items()):
        r = next((r for r in by_student.get(sid, []) if r.opp_id == oid), None)
        if r is not None:
            X.append(features(r))
            y.append(lab)
    pos = sum(y)
    if len(y) < config.ML_MIN_LABELS or min(pos, len(y) - pos) < config.ML_MIN_PER_CLASS:
        return None
    from sklearn.linear_model import LogisticRegression
    Xa = np.asarray(X, dtype=float)
    mean, scale = Xa.mean(axis=0), Xa.std(axis=0)
    scale[scale == 0] = 1.0
    m = LogisticRegression(C=1.0, class_weight="balanced", max_iter=1000).fit((Xa - mean) / scale, np.asarray(y))
    return Model(mean=mean, scale=scale, coef=m.coef_[0], intercept=float(m.intercept_[0]), n=len(y), positives=pos)


def apply(rows: list[MatchRow], ctx: Context) -> list[MatchRow]:
    model = ctx.model
    if not ctx.v3.get("ml") or not isinstance(model, Model):
        return rows
    out = []
    for r in rows:
        p = model.chance(r)
        out.append(adjust.put(r, "ml", model.weight * (p - 0.5) * 2 * config.ML_MAX, ml=round(p, 3)))
    return out


def describe(model: Model | None, labelled: dict[tuple[str, str], int]) -> dict:
    """What the Settings page shows: is it learning yet, from how much, and what it has learned."""
    pos = sum(labelled.values())
    base = {"labels": len(labelled), "yes": pos, "no": len(labelled) - pos, "needed": config.ML_MIN_LABELS,
            "needed_each": config.ML_MIN_PER_CLASS, "max_nudge": config.ML_MAX, "on": config.V3.get("ml", False)}
    if model is None:
        return {**base, "trained": False}
    words = list(FEATURES.values())
    ranked = sorted(zip(words, model.coef), key=lambda x: -abs(x[1]))
    return {**base, "trained": True, "weight": round(model.weight, 2),
            "learned": [{"what": w, "effect": "helps" if c > 0 else "hurts", "strength": round(abs(float(c)), 2)} for w, c in ranked[:6]]}
