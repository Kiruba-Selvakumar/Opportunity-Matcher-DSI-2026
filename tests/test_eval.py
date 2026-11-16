import json

from eval.baseline import baseline_top, jaccard, tokens
from eval.evaluate import compute, precision, to_markdown, violation_rate
from eval.make_label_sheet import pick_students
from matcher.config import PATHS
from matcher.schema import Student


def test_precision_hand_computed():
    lists = {"S1": ["A", "B", "C", "D", "E"]}
    labels = {("S1", "A"): "good", ("S1", "B"): "good", ("S1", "C"): "ok", ("S1", "D"): "bad", ("S1", "E"): "bad"}
    assert precision(lists, labels) == {"strict": 0.4, "lenient": 0.6, "items": 5}
    assert precision(lists, labels, reviewed_only={("S1", "A")}) == {"strict": 1.0, "lenient": 1.0, "items": 1}
    assert precision({"S1": ["A"]}, {})["strict"] is None


def test_jaccard_tokens():
    assert jaccard(tokens("Python, SQL"), tokens("python + sql, git")) == 2 / 3


def test_baseline_top5_length(pipeline_dir):
    import pandas as pd
    s = pd.read_csv(PATHS["students_raw"], dtype=str, keep_default_na=False)
    o = pd.read_csv(PATHS["opportunities_raw"], dtype=str, keep_default_na=False)
    top = baseline_top(s, o)
    assert len(top) == 100 and all(len(v) == 5 for v in top.values())


def test_label_pick_rules(pipeline_dir):
    students = [Student(**d) for d in json.loads(PATHS["students"].read_text())]
    picked = pick_students(students)
    assert len(picked) == 20 and {"S001", "S002", "S003"} <= set(picked)
    by = {s.student_id: s for s in students}
    assert sum(not by[i].branch.startswith("CSE") for i in picked) >= 4


def test_our_violation_rate_is_zero_and_report(pipeline_dir):
    from eval import auto_label, make_label_sheet
    make_label_sheet.main()
    auto_label.main()
    res = compute()
    assert res["violation_rate"]["ours"] == 0
    assert res["labels_auto"] > 0 and res["labels_human_reviewed"] == 0
    md = to_markdown(res)
    assert "Keyword baseline" in md and "not measured yet" in md


def test_version_comparison_is_honest_without_human_labels(pipeline_dir):
    from eval import auto_label, make_label_sheet
    make_label_sheet.main(); auto_label.main()
    res = compute()
    v = res["matching_versions"]
    assert 0 <= v["same_first_choice"] <= 1 and 0 <= v["mean_top5_overlap"] <= 1
    assert v["human_precision"]["v2"]["strict"] is None and "cannot be judged" in v["note"]
    assert "Matching v1 and v2" in to_markdown(res)
