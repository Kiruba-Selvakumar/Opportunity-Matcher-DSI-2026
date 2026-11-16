"""Metrics: precision at 5 (strict and lenient), violation rate, coverage, timing."""
from __future__ import annotations

import csv
import json
from collections import defaultdict
from pathlib import Path

from matcher.config import PATHS
from matcher.embed import get_encoder
from matcher.rank import top_k
from matcher.related import Context
from matcher.score import build_context, load_clean, opp_vectors, score_student

from .baseline import baseline_top, load_raw


def precision(lists: dict[str, list[str]], labels: dict[tuple[str, str], str], reviewed_only: set | None = None) -> dict:
    """Share of labelled items in each top list that are good (strict) or good/ok (lenient)."""
    good = okish = n = 0
    for sid, opp_ids in lists.items():
        for oid in opp_ids:
            key = (sid, oid)
            if key not in labels or (reviewed_only is not None and key not in reviewed_only):
                continue
            n += 1
            good += labels[key] == "good"
            okish += labels[key] in ("good", "ok")
    if n == 0:
        return {"strict": None, "lenient": None, "items": 0}
    return {"strict": round(good / n, 3), "lenient": round(okish / n, 3), "items": n}


def read_labels(path: Path) -> list[dict]:
    if not Path(path).exists():
        return []
    with open(path, newline="") as f:
        return [r for r in csv.DictReader(f) if (r.get("label") or "").strip()]


def read_timing(path: Path) -> dict:
    if not Path(path).exists():
        return {}
    by = defaultdict(list)
    with open(path, newline="") as f:
        for r in csv.DictReader(f):
            try:
                by[r["method"].strip()].append(float(r["seconds"]))
            except (KeyError, ValueError):
                continue
    return {m: round(sum(v) / len(v), 1) for m, v in by.items() if v}


def violation_rate(lists: dict[str, list[str]], rows_by_student: dict) -> float:
    total = bad = 0
    for sid, opp_ids in lists.items():
        for oid in opp_ids:
            total += 1
            bad += any(c.status == "fail" for c in rows_by_student[sid][oid].checks.values())
    return round(bad / total, 3) if total else 0.0


def avg_coverage(lists: dict[str, list[str]], rows_by_student: dict) -> float:
    vals = [rows_by_student[sid][oid].coverage for sid, ids in lists.items() for oid in ids]
    return round(sum(vals) / len(vals), 3) if vals else 0.0


def compare_versions(students, opps, norm, enc, ov, labels: dict, reviewed: set) -> dict:
    """Top 5 under the old score (v1) and the new score (v2), side by side.

    The auto labels are built from plain coverage, so they favour any change that raises coverage. They are NOT used
    to judge v2. Only human-reviewed labels are, and the report says so when there are none.
    """
    ctx1, ctx2 = Context.v1(opps, norm), build_context(opps, norm)
    ov1 = opp_vectors(opps, norm, enc, tech=False)               # v1 compared whole skill profiles, soft skills included
    top1, top2, same_first, jac = {}, {}, 0, []
    for s in students:
        a = [r.opp_id for r in top_k(score_student(s, opps, norm, enc, ov1, ctx1))]
        b = [r.opp_id for r in top_k(score_student(s, opps, norm, enc, ov, ctx2))]
        top1[s.student_id], top2[s.student_id] = a, b
        same_first += bool(a and b and a[0] == b[0])
        union = set(a) | set(b)
        jac.append(len(set(a) & set(b)) / len(union) if union else 1.0)
    reviewed_students = {sid for sid, _ in reviewed}
    p1 = precision({k: v for k, v in top1.items() if k in reviewed_students}, labels, reviewed)
    p2 = precision({k: v for k, v in top2.items() if k in reviewed_students}, labels, reviewed)
    return {"students": len(students), "same_first_choice": round(same_first / len(students), 3),
            "mean_top5_overlap": round(sum(jac) / len(jac), 3),
            "human_precision": {"v1": p1, "v2": p2},
            "note": ("Judged on human-reviewed labels only." if reviewed else
                     "No human-reviewed labels yet, so v2 cannot be judged as better or worse. Review eval/labels.csv.")}


def compute() -> dict:
    students, opps, norm = load_clean()
    enc = get_encoder()
    ov = opp_vectors(opps, norm, enc)
    rows_by = {s.student_id: {m.opp_id: m for m in score_student(s, opps, norm, enc, ov)} for s in students}
    top = json.loads(PATHS["top5"].read_text())
    ours = {sid: [m["opp_id"] for m in ms] for sid, ms in top.items()}
    base = baseline_top(*load_raw())

    labels_rows = read_labels(PATHS["labels"])
    labels = {(r["student_id"], r["opp_id"]): r["label"].strip().lower() for r in labels_rows}
    reviewed = {(r["student_id"], r["opp_id"]) for r in labels_rows if (r.get("labeller") or "").strip().lower()
                not in ("", "auto")}
    labelled_students = {sid for sid, _ in labels}
    ours_l = {s: v for s, v in ours.items() if s in labelled_students}
    base_l = {s: v for s, v in base.items() if s in labelled_students}

    timing = read_timing(PATHS["timing"])
    res = {
        "students_labelled": len(labelled_students),
        "labels_human_reviewed": len(reviewed),
        "labels_auto": len(labels) - len(reviewed),
        "precision_at_5_human_reviewed": {"ours": precision(ours_l, labels, reviewed),
                                          "baseline": precision(base_l, labels, reviewed)},
        "precision_at_5_all_labels_incl_auto": {"ours": precision(ours_l, labels),
                                                "baseline": precision(base_l, labels)},
        "violation_rate": {"ours": violation_rate(ours, rows_by), "baseline": violation_rate(base, rows_by)},
        "avg_coverage_top5": {"ours": avg_coverage(ours, rows_by), "baseline": avg_coverage(base, rows_by)},
        "students_with_fewer_than_5_matches": sum(1 for v in ours.values() if len(v) < 5),
        "timing_mean_seconds": timing or "not measured yet",
        "matching_versions": compare_versions(students, opps, norm, enc, ov, labels, reviewed),
    }
    return res


def _fmt(x) -> str:
    return "not reviewed yet" if x is None else f"{x:.0%}" if isinstance(x, float) and x <= 1 else str(x)


def to_markdown(res: dict) -> str:
    h = res["precision_at_5_human_reviewed"]
    a = res["precision_at_5_all_labels_incl_auto"]
    t = res["timing_mean_seconds"]
    lines = [
        "# Match quality results", "",
        f"Labelled students: {res['students_labelled']}. Labels reviewed by a human: {res['labels_human_reviewed']}. "
        f"Labels still marked auto: {res['labels_auto']}.", "",
        "The headline precision uses human-reviewed labels only. Rows still marked auto are shown separately.", "",
        "| Metric | Our system | Keyword baseline |", "|---|---|---|",
        f"| Precision at 5, strict (human reviewed) | {_fmt(h['ours']['strict'])} | {_fmt(h['baseline']['strict'])} |",
        f"| Precision at 5, lenient (human reviewed) | {_fmt(h['ours']['lenient'])} | {_fmt(h['baseline']['lenient'])} |",
        f"| Precision at 5, strict (incl. auto labels) | {_fmt(a['ours']['strict'])} | {_fmt(a['baseline']['strict'])} |",
        f"| Precision at 5, lenient (incl. auto labels) | {_fmt(a['ours']['lenient'])} | {_fmt(a['baseline']['lenient'])} |",
        f"| Constraint violation rate | {_fmt(res['violation_rate']['ours'])} | {_fmt(res['violation_rate']['baseline'])} |",
        f"| Average skill coverage of top 5 | {res['avg_coverage_top5']['ours']:.2f} | {res['avg_coverage_top5']['baseline']:.2f} |",
        "", f"Students with fewer than 5 eligible matches: {res['students_with_fewer_than_5_matches']}.", "",
    ]
    v = res["matching_versions"]
    lines += ["", "## Matching v1 and v2", "",
              f"Same first choice for {v['same_first_choice']:.0%} of students. Average overlap of the top 5: {v['mean_top5_overlap']:.0%}.",
              f"Precision at 5 on human-reviewed labels: v1 {_fmt(v['human_precision']['v1']['strict'])}, v2 {_fmt(v['human_precision']['v2']['strict'])}.",
              v["note"], ""]
    if isinstance(t, dict):
        lines.append("Time to match one student (mean seconds): " + ", ".join(f"{m} {s}s" for m, s in t.items()) + ".")
    else:
        lines.append("Time to match one student: not measured yet.")
    return "\n".join(lines) + "\n"


def main() -> None:
    res = compute()
    PATHS["results_json"].write_text(json.dumps(res, indent=1))
    PATHS["results_md"].write_text(to_markdown(res))
    print(to_markdown(res))


if __name__ == "__main__":
    main()
