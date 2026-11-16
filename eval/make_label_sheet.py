"""Write eval/labels_template.csv: 20 students, union of our top 5 and the baseline top 5, in random order."""
from __future__ import annotations

import csv
import json
import random

from matcher.config import PATHS, SEED
from matcher.schema import Opportunity, Student

from .baseline import baseline_top, load_raw

COLUMNS = ["student_id", "opp_id", "student_summary", "opp_summary", "label", "labeller", "comment"]


def student_summary(s: Student, skills: list[str]) -> str:
    reloc = {True: "can relocate", False: "cannot relocate", None: "relocation unknown"}[s.can_relocate]
    budget = "budget unknown" if s.budget is None else f"budget Rs {s.budget}"
    limits = ", ".join(s.family_limits) or "no family limits"
    return (f"{s.branch}, CGPA {s.cgpa if s.cgpa is not None else 'unknown'}, skills: {', '.join(skills) or 'none'}, "
            f"town {s.college_town}, {reloc}, {budget}, {limits}")


def opp_summary(o: Opportunity, skills: list[str]) -> str:
    where = "Remote" if o.mode == "remote" else f"{o.city} ({o.mode})"
    return (f"{o.title} [{o.type}], {where}, needs: {', '.join(skills) or 'none listed'}, "
            f"cost Rs {o.upfront_cost}, night shift {'yes' if o.night_shift else 'no'}, safety {o.safety_score}/5")


def pick_students(students: list[Student], n: int = 20, seed: int = SEED) -> list[str]:
    rnd = random.Random(seed)
    chosen = ["S001", "S002", "S003"]
    ids = [s.student_id for s in students]
    non_cse = [s.student_id for s in students if not s.branch.startswith("CSE") and s.student_id not in chosen]
    have = sum(1 for sid in chosen if not next(s for s in students if s.student_id == sid).branch.startswith("CSE"))
    for sid in rnd.sample(non_cse, max(0, 4 - have)):
        chosen.append(sid)
    rest = [i for i in ids if i not in chosen]
    chosen += rnd.sample(rest, n - len(chosen))
    return sorted(chosen)


def main() -> None:
    students = [Student(**d) for d in json.loads(PATHS["students"].read_text())]
    opps = {d["opp_id"]: Opportunity(**d) for d in json.loads(PATHS["opportunities"].read_text())}
    norm = json.loads(PATHS["normalized"].read_text())
    top = json.loads(PATHS["top5"].read_text())
    base = baseline_top(*load_raw())
    by_id = {s.student_id: s for s in students}
    rows = []
    for sid in pick_students(students):
        ids = {m["opp_id"] for m in top[sid]} | set(base[sid])
        for oid in sorted(ids):
            rows.append([sid, oid, student_summary(by_id[sid], norm["students"][sid]["skills"]),
                         opp_summary(opps[oid], norm["opportunities"][oid]["skills"]), "", "", ""])
    random.Random(SEED).shuffle(rows)
    PATHS["labels_template"].parent.mkdir(parents=True, exist_ok=True)
    with open(PATHS["labels_template"], "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(COLUMNS)
        w.writerows(rows)
    print(f"wrote {len(rows)} rows to {PATHS['labels_template']}")


if __name__ == "__main__":
    main()
