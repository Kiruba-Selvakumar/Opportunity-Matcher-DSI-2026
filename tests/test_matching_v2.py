import csv

import pytest

from matcher import config
from matcher.config import PATHS
from matcher.embed import get_encoder
from matcher.explain import template_reason
from matcher.generate_opportunities import FAMILIES
from matcher.rank import to_top_matches, top_k
from matcher.recommend import close_the_gap, fit_label
from matcher.related import Context, congestion_penalty, prior_adjustment
from matcher.schema import Decision
from matcher.score import coverage, score_student, soft_terms, weighted_coverage
from matcher.skills import load_vocab

from .conftest import make_opp, make_student

ALL_OFF = {k: False for k in config.V2}


def ctx(**kw):
    flags = kw.pop("flags", dict(config.V2))
    return Context(flags=flags, **kw)


def test_rare_skills_count_more():
    c = ctx(idf={"SQL": 1.0, "Kotlin": 2.5})
    kotlin_only, _, _, _ = weighted_coverage(["Kotlin"], ["SQL", "Kotlin"], [], c)
    sql_only, _, _, _ = weighted_coverage(["SQL"], ["SQL", "Kotlin"], [], c)
    assert kotlin_only == pytest.approx(2.5 / 3.5, abs=1e-3) and sql_only == pytest.approx(1 / 3.5, abs=1e-3)
    assert kotlin_only > sql_only
    assert weighted_coverage(["Kotlin"], ["SQL", "Kotlin"], [], ctx(idf=c.idf, flags=ALL_OFF))[0] == 0.5   # plain share when off


def test_nice_to_have_counts_half():
    c = ctx(flags={**ALL_OFF})
    assert weighted_coverage(["Python"], ["Python", "Git"], ["Git"], c)[0] == pytest.approx(1 / 1.5, abs=1e-3)
    assert weighted_coverage(["Git"], ["Python", "Git"], ["Git"], c)[0] == pytest.approx(0.5 / 1.5, abs=1e-3)


def test_related_skills_give_partial_credit_and_are_listed():
    c = ctx(related={("MySQL", "SQL"): 0.8}, categories={"MySQL": "database", "SQL": "programming", "Git": "tools_devops"})
    cov, overlap, missing, partial = weighted_coverage(["MySQL"], ["SQL"], [], c)
    assert (cov, overlap, missing) == (0.8, [], []) and partial == [{"have": "MySQL", "need": "SQL", "credit": 0.8}]
    cov, overlap, missing, partial = weighted_coverage(["Git"], ["SQL"], [], c)
    assert (cov, missing, partial) == (0.0, ["SQL"], [])
    assert weighted_coverage(["MySQL"], ["SQL"], [], ctx(related=c.related, flags=ALL_OFF))[0] == 0.0


def test_same_area_gives_a_small_credit_and_stays_missing():
    real = Context.build([], {"opportunities": {}})
    cov, overlap, missing, partial = weighted_coverage(["Python"], ["Java"], [], real)
    assert cov == config.SAME_CATEGORY_CREDIT and missing == ["Java"] and partial[0]["credit"] == 0.2


def test_the_best_credit_wins_and_never_exceeds_one():
    c = ctx(related={("MySQL", "SQL"): 0.8, ("PostgreSQL", "SQL"): 0.8, ("SQLite", "SQL"): 0.9})
    cov, _, _, partial = weighted_coverage(["MySQL", "PostgreSQL", "SQLite"], ["SQL"], [], c)
    assert cov == 0.9 and len(partial) == 1
    assert weighted_coverage(["SQL"], ["SQL"], [], c)[0] == 1.0


def test_soft_terms_stay_inside_their_caps():
    c = ctx(branch_fit={("CSE", "Python Developer"): 0.05})
    opp = make_opp(job_family="Python Developer", city="Warangal", mode="onsite")
    s = make_student(branch="CSE", college_town="Khammam", can_relocate=True, cgpa=5.5)
    t = soft_terms(s, opp, {}, c)
    assert t == {"branch_fit": 0.05, "home_state": 0.02, "low_cgpa": -0.02}
    assert sum(abs(v) for v in t.values()) <= 0.09 + 1e-9
    assert soft_terms(s, make_opp(city="Pune", job_family="x"), {}, c) == {"low_cgpa": -0.02}   # other state: no home bonus
    assert soft_terms(s, opp, {}, ctx(flags=ALL_OFF)) == {}
    assert "low_cgpa" not in soft_terms(s, make_opp(type="training", job_family="x"), {}, c)    # only for jobs


def test_congestion_only_above_the_threshold_and_capped():
    opp = make_opp(opp_id="J1", openings=2)                 # limit = 3 x 2 = 6
    assert congestion_penalty(ctx(load={"J1": 6}), opp) == 0.0
    assert 0 < congestion_penalty(ctx(load={"J1": 9}), opp) < config.CONGESTION_MAX
    assert congestion_penalty(ctx(load={"J1": 600}), opp) == config.CONGESTION_MAX
    assert congestion_penalty(ctx(load={"J1": 600}, flags=ALL_OFF), opp) == 0.0


def test_staff_prior_needs_enough_decisions_and_is_capped():
    assert prior_adjustment(ctx(prior={"X": (4, 4)}), "X") == (0.0, None)           # only 4 decisions
    adj, note = prior_adjustment(ctx(prior={"X": (9, 9)}), "X")
    assert 0 < adj <= config.PRIOR_MAX and note == "Staff accepted 9 of 9 similar matches"
    low, _ = prior_adjustment(ctx(prior={"X": (0, 9)}), "X")
    assert -config.PRIOR_MAX <= low < 0
    assert prior_adjustment(ctx(prior={"X": (9, 9)}, flags=ALL_OFF), "X") == (0.0, None)


def test_the_prior_ignores_flags_and_what_if_decisions():
    opps = [make_opp(opp_id="O1", job_family="Fam")]
    ds = [Decision(student_id=f"S{i}", opp_id="O1", decision="accept") for i in range(4)]
    ds += [Decision(student_id="S9", opp_id="O1", decision="flag", note="x"), Decision(student_id="S8", opp_id="O1", decision="accept", what_if=True)]
    c = Context.build(opps, {"opportunities": {"O1": {"skills": []}}}, decisions=ds)
    assert c.prior["Fam"] == (4, 4)


def test_switching_everything_off_gives_the_v1_score(students_small, opps_small, norm_small):
    enc = get_encoder()
    s = students_small[0]
    v1 = {r.opp_id: r for r in score_student(s, opps_small, norm_small, enc, ctx=Context.v1(opps_small, norm_small))}
    for o in opps_small:
        cov, overlap, missing = coverage(norm_small["students"][s.student_id]["skills"], norm_small["opportunities"][o.opp_id]["skills"])
        r = v1[o.opp_id]
        assert (r.coverage, r.overlap, r.missing, r.adjustments, r.related) == (cov, overlap, missing, {}, [])


def test_scores_stay_in_range_and_the_breakdown_adds_up(students_small, opps_small, norm_small):
    enc = get_encoder()
    for s in students_small:
        for r in score_student(s, opps_small, norm_small, enc):
            assert 0 <= r.final_score <= 1
            expect = min(1, max(0, r.base_score + sum(r.adjustments.values()) - r.penalty_hours - r.penalty_safety))
            assert r.final_score == pytest.approx(expect, abs=0.002)


def test_gap_closers_are_eligible_training_that_covers_missing_skills(students_small, opps_small, norm_small):
    enc = get_encoder()
    s = next(x for x in students_small if x.student_id == "S004")
    rows = score_student(s, opps_small, norm_small, enc)
    got = close_the_gap(rows, norm_small, ["Python", "Selenium", "Cooking"])
    assert got and all(g["type"] in ("training", "mentor") and g["covers"] for g in got) and len(got) <= 2
    by = {r.opp_id: r for r in rows}
    assert all(by[g["opp_id"]].eligible for g in got)
    assert got[0]["covers"] and close_the_gap(rows, norm_small, []) == []


def test_fit_labels():
    assert fit_label(0.7, False) == "Strong fit" and fit_label(0.45, False) == "Good fit"
    assert fit_label(0.2, True) == "Stretch" and fit_label(0.2, False) == "Possible fit"


def test_reasons_mention_related_crowded_and_prior(students_small, opps_small, norm_small):
    from matcher.schema import CheckResult, TopMatch
    ok = CheckResult(status="pass")
    m = TopMatch(rank=1, opp_id="O1", title="t", type="job", city="Remote", mode="remote", final_score=0.5, overlap=["Python"],
                 missing=[], checks={"location": ok, "budget": ok, "language": ok, "family": ok}, reason="",
                 related=[{"have": "MySQL", "need": "SQL", "credit": 0.8}], crowded=True, prior_note="Staff accepted 7 of 9 similar matches")
    text = template_reason(m, make_student(), make_opp(city="Remote", mode="remote"))
    assert "Your MySQL also counts for SQL" in text and "Many students have already applied" in text and "Staff accepted 7 of 9" in text


def test_reference_files_are_consistent():
    vocab = set(load_vocab())
    with open(PATHS["related_skills"]) as f:
        pairs = list(csv.DictReader(f))
    assert len(pairs) >= 80
    for p in pairs:
        assert p["have"] in vocab and p["need"] in vocab and p["have"] != p["need"], p
        assert 0 < float(p["credit"]) < 1, p
    assert len({(p["have"], p["need"]) for p in pairs}) == len(pairs)               # no duplicate pairs
    families = {f[0] for f in FAMILIES}
    with open(PATHS["branch_fit"]) as f:
        for r in csv.DictReader(f):
            assert r["job_family"] in families and 0 < float(r["bonus"]) <= config.BRANCH_FIT_MAX, r


def test_training_that_teaches_nothing_is_capped_below_the_shown_threshold():
    from matcher.schema import CheckResult
    from matcher.training import finalize
    from matcher.schema import MatchRow
    ok = CheckResult(status="pass")
    chk = {"location": ok, "budget": ok, "language": ok, "family": ok}
    job = MatchRow(student_id="S", opp_id="J", type="job", title="j", org_name="o", city="Remote", mode="remote", skill_sim=0.5, coverage=0.5,
                   missing=["Power BI"], base_score=0.5, final_score=0.5, eligible=True, checks=chk)
    mk = lambda oid: MatchRow(student_id="S", opp_id=oid, type="training", title=oid, org_name="o", city="Remote", mode="remote", skill_sim=0.9,
                              coverage=0.9, base_score=0.9, final_score=0.9, eligible=True, checks=chk)  # noqa: E731
    norm = {"opportunities": {"T1": {"skills": ["Power BI"]}, "T2": {"skills": ["Excel"]}}}
    out = {r.opp_id: r for r in finalize([job, mk("T1"), mk("T2")], norm, Context(flags=dict(config.V2)))}
    assert out["T1"].teaches == ["Power BI"] and out["T1"].final_score > config.MIN_SHOW_SCORE
    assert out["T2"].teaches == [] and out["T2"].final_score <= config.MIN_SHOW_SCORE / 2     # high similarity does not rescue it
    assert finalize([job, mk("T2")], norm, Context(flags=ALL_OFF))[1].final_score == 0.9       # off means untouched
