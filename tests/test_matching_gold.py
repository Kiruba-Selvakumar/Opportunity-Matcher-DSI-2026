"""Does matching give answers a placement officer would agree with? Checks on the real sample data, not on fixtures."""
import random

import numpy as np
import pytest

from api import state as S
from matcher import config
from matcher.config import PATHS
from matcher.embed import get_encoder
from matcher.recommend import close_the_gap
from matcher.related import Context
from matcher.score import opp_vectors, student_vector, weighted_coverage
from matcher.skills import load_categories, technical


@pytest.fixture(scope="module")
def st(pipeline_dir, tmp_path_factory):
    """The state of the pipeline data alone: an empty database, so listings from other tests cannot change the answers."""
    old = PATHS["db"]
    PATHS["db"] = tmp_path_factory.mktemp("gold") / "gold.db"
    try:
        yield S.load_state()
    finally:
        PATHS["db"] = old


def family(st, m):
    return st.opps[m.opp_id].job_family


def test_the_hero_students_get_answers_that_make_sense(st):
    s1 = st.matches("S001")                                    # Python, SQL, Excel, cannot leave Khammam
    assert [family(st, m) for m in s1[:2]] == ["Data Analyst", "Data Analyst"] and s1[0].final_score > 0.7
    assert all(m.mode == "remote" or m.city == "Khammam" for m in s1)
    s3 = st.matches("S003")                                    # embedded systems, no money, not sure about moving
    assert s3 and st.opps[s3[0].opp_id].title == "Alumni Mentor: Embedded Systems" and s3[0].final_score > 0.8
    assert len(s3) <= 2                                        # no padding with weak matches
    s7 = st.matches("S007")                                    # data science student
    assert family(st, s7[0]) == "Data Analyst"


def test_nothing_below_the_minimum_is_ever_shown_and_types_are_spread(st):
    for sid in st.students:
        ms = st.matches(sid)
        assert all(m.final_score >= config.MIN_SHOW_SCORE for m in ms), sid
        assert max([sum(1 for m in ms if m.type == t) for t in ("job", "training", "mentor")]) <= 3, sid
        assert [m.rank for m in ms] == list(range(1, len(ms) + 1))


def test_a_student_with_no_top_match_can_still_browse_what_is_open(st):
    none = [sid for sid in st.students if not st.matches(sid)]
    assert none, "the sample data should have some students with no strong match"
    assert any(any(r.eligible for r in st.rows_by_student[sid]) for sid in none)    # something is open, it just is not a strong fit


def test_training_is_shown_only_for_what_it_teaches(st):
    seen = 0
    for sid in st.students:
        for m in st.matches(sid):
            if m.type == "training":
                seen += 1
                assert m.teaches, (sid, m.title)                 # a training with nothing to teach this student is never recommended
                assert "Teaches" in m.reason
    assert seen > 0


def test_gap_closers_never_repeat_or_suggest_the_match_itself(st):
    for sid in st.students:
        for m in st.matches(sid):
            titles = [g["title"] for g in m.gap_closers]
            assert len(titles) == len(set(titles)) and m.opp_id not in [g["opp_id"] for g in m.gap_closers]
            assert m.type == "job" or m.gap_closers == []
            assert all(set(g["covers"]) <= set(m.missing) for g in m.gap_closers)


def test_soft_skills_never_make_two_profiles_look_alike(st):
    enc, ctx = get_encoder(), st.ctx
    only_soft = student_vector(["English Communication", "Telugu Communication", "Teamwork"], enc, ctx)
    assert not np.any(only_soft)
    vecs = opp_vectors(list(st.opps.values()), st.norm, enc)
    support = [o for o in st.opps.values() if o.job_family == "Technical Support"][0]
    assert np.allclose(vecs[support.opp_id], opp_vectors([support], st.norm, enc)[support.opp_id])
    assert technical(["Python", "English Communication", "AMCAT Certified", "SQL"]) == ["Python", "SQL"]
    cats = load_categories()
    assert cats["English Communication"] == "soft" and cats["AMCAT Certified"] == "local"


def test_more_skills_never_lower_coverage(st):
    rnd = random.Random(7)
    pool = sorted({s for n in st.norm["opportunities"].values() for s in n["skills"]})
    for _ in range(300):
        oid = rnd.choice(list(st.opps))
        n = st.norm["opportunities"][oid]
        have = rnd.sample(pool, rnd.randint(0, 6))
        extra = have + [rnd.choice(pool)]
        a = weighted_coverage(have, n["skills"], n.get("nice", []), st.ctx)[0]
        b = weighted_coverage(extra, n["skills"], n.get("nice", []), st.ctx)[0]
        assert 0 <= a <= b <= 1, (have, extra, oid)


def test_having_every_required_skill_gives_full_coverage_and_none_gives_zero(st):
    for oid, n in st.norm["opportunities"].items():
        if not n["skills"]:
            continue
        assert weighted_coverage(n["skills"], n["skills"], n.get("nice", []), st.ctx)[0] == 1.0
        none = weighted_coverage([], n["skills"], n.get("nice", []), st.ctx)
        assert none[0] == 0.0 and sorted(none[2]) == sorted(n["skills"])


def test_the_score_is_stable_for_the_same_input(st):
    a = [(m.opp_id, m.final_score) for m in st.matches("S002")]
    S2 = S.load_state()
    assert a == [(m.opp_id, m.final_score) for m in S2.matches("S002")]
