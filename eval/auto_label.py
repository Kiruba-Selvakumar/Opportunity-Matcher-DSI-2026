"""Pre-fill labels with a rule so humans can review faster. Writes eval/labels.csv with labeller=auto."""
from __future__ import annotations

import csv
import json

from matcher.config import PATHS
from matcher.embed import get_encoder
from matcher.schema import MatchRow
from matcher.score import load_clean, opp_vectors, score_student


def rule_label(row: MatchRow) -> str:
    if any(c.status == "fail" for c in row.checks.values()):
        return "bad"
    if row.coverage >= 0.5:
        return "good"
    return "ok"


def main() -> None:
    students, opps, norm = load_clean()
    by_id = {s.student_id: s for s in students}
    enc = get_encoder()
    ov = opp_vectors(opps, norm, enc)
    cache: dict[str, dict[str, MatchRow]] = {}
    with open(PATHS["labels_template"], newline="") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        sid = r["student_id"]
        if sid not in cache:
            cache[sid] = {m.opp_id: m for m in score_student(by_id[sid], opps, norm, enc, ov)}
        r["label"] = rule_label(cache[sid][r["opp_id"]])
        r["labeller"] = "auto"
    with open(PATHS["labels"], "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"wrote {len(rows)} auto labels to {PATHS['labels']}. Review every row and set labeller to your name.")


if __name__ == "__main__":
    main()
