import json
import re
import time

import pandas as pd

from matcher.config import PATHS


def test_full_pipeline(pipeline_dir):
    students = json.loads(PATHS["students"].read_text())
    opps = json.loads(PATHS["opportunities"].read_text())
    assert len(students) == 100 and len(opps) == 50
    assert len(pd.read_csv(PATHS["pair_scores"])) == 5000
    top = json.loads(PATHS["top5"].read_text())
    eligible = pd.read_csv(PATHS["pair_scores"]).groupby("student_id")["eligible"].sum()
    for sid, n in eligible.items():
        if n >= 1:
            assert len(top[sid]) >= 1
        for m in top[sid]:
            assert m["reason"].strip()
            assert all(c["status"] != "fail" for c in m["checks"].values())


def test_no_pii_in_clean_or_derived(pipeline_dir):
    names = pd.read_csv(PATHS["contacts"], dtype=str)["name"].tolist()
    for folder in (PATHS["students"].parent, PATHS["top5"].parent):
        for f in folder.iterdir():
            if f.suffix not in {".json", ".csv", ".jsonl"}:
                continue
            text = f.read_text()
            assert not re.search(r"[6-9]\d{9}", text.replace("\n", " ")), f.name
            assert "@example.com" not in text, f.name
            for n in names:
                assert n not in text, (f.name, n)


def test_pipeline_is_fast_and_deterministic(pipeline_dir, tmp_path):
    from matcher import config, pipeline
    before = PATHS["top5"].read_text()
    t = time.perf_counter()
    pipeline.run(quiet=True, no_llm=True)
    assert time.perf_counter() - t < 60
    assert PATHS["top5"].read_text() == before
