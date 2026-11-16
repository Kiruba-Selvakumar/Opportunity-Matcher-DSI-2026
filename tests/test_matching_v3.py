"""Matching v3: upskilling preference, the learned nudge, standing among students, and the learning plan."""
from datetime import date

import pytest

from matcher import adjust, config, learn, learning_plan, relative, upskill
from matcher.embed import get_encoder
from matcher.related import Context
from matcher.score import score_student

from .conftest import make_opp, make_student


def scored(student, opps, norm):
    ctx = Context.build(opps, norm)
    return score_student(student, opps, norm, get_encoder(), ctx=ctx), ctx


def setup_gap():
    s = make_student(student_id="X1", budget=5000)
    job = make_opp(opp_id="O1", mode="remote", city="Remote")
    course = make_opp(opp_id="T1", type="training", title="Python Basics", mode="remote", city="Remote", pay_min=None, pay_max=None,
                      starts_on="2026-01-05", duration_weeks=4, batch_every_weeks=4)
    norm = {"students": {"X1": {"skills": ["Excel", "SQL"]}},
            "opportunities": {"O1": {"skills": ["SQL", "Power BI", "Python"], "nice": []}, "T1": {"skills": ["Python"], "nice": []}}}
    return s, [job, course], norm


def test_adjust_put_replaces_and_recomputes():
    s, opps, norm = setup_gap()
    rows, _ = scored(s, opps, norm)
    job = next(r for r in rows if r.opp_id == "O1")
    a = adjust.put(job, "test", 0.05)
    b = adjust.put(a, "test", 0.02)
    assert b.adjustments["test"] == 0.02 and round(b.final_score - job.final_score, 3) == 0.02
    assert adjust.without(b, "test") == job.final_score
    assert "test" not in adjust.put(b, "test", 0.0).adjustments


def test_upskill_explains_each_missing_skill(monkeypatch):
    s, opps, norm = setup_gap()
    seen = []

    def fake_ease(credit, training):
        seen.append((credit, training))
        return 1.0 if training else credit
    monkeypatch.setattr(upskill, "ease", fake_ease)
    rows, _ = scored(s, opps, norm)
    job = next(r for r in rows if r.opp_id == "O1")
    steps = {x["skill"]: x for x in job.upskill["steps"]}
    assert set(steps) == {"Power BI", "Python"}
    assert steps["Power BI"]["from"] == "Excel" and steps["Power BI"]["via"] is None           # Excel counts partly toward Power BI
    assert steps["Python"]["via"]["opp_id"] == "T1" and steps["Python"]["ease"] == 1.0
    assert ({"type": "training", "cost": 0, "weeks": 4, "budget": 5000} in [t for _, t in seen])
    assert 0 < job.upskill["reach"] <= 1 and job.upskill["potential"] > job.coverage
    assert abs(job.adjustments["upskill"] - config.UPSKILL_MAX * (job.upskill["potential"] - job.coverage)) < 2e-4   # potential is rounded


def test_upskill_is_bounded_whatever_ease_returns(monkeypatch):
    s, opps, norm = setup_gap()
    monkeypatch.setattr(upskill, "ease", lambda c, t: 7.0)                                     # a wrong ease cannot run away
    rows, _ = scored(s, opps, norm)
    assert next(r for r in rows if r.opp_id == "O1").adjustments["upskill"] <= config.UPSKILL_MAX


def test_standing_math():
    field = [0.2, 0.4, 0.4, 0.7, 0.9]
    assert relative.standing(0.9, field) == {"rank": 1, "of": 5, "percentile": 1.0}
    assert relative.standing(0.4, field) == {"rank": 3, "of": 5, "percentile": 0.5}                # ties share the better rank
    assert relative.standing(0.2, field)["percentile"] == 0.0
    assert relative.standing(0.95, field, in_field=False) == {"rank": 1, "of": 6, "percentile": 1.0}


def test_standing_nudge_needs_a_field(monkeypatch):
    monkeypatch.setattr(upskill, "ease", lambda c, t: 0.0)                                     # only standing moves the score here
    s, opps, norm = setup_gap()
    rows, ctx = scored(s, opps, norm)
    ctx.competition = {"O1": [0.1, 0.2, 0.3]}
    small = next(r for r in relative.apply(rows, ctx) if r.opp_id == "O1")
    assert small.standing["rank"] == 1 and "standing" not in small.adjustments                  # 3 students: shown, not used
    ctx.competition = {"O1": [0.1, 0.2, 0.3, 0.35, 0.36, 0.95]}
    big = next(r for r in relative.apply(rows, ctx) if r.opp_id == "O1")
    assert big.standing["of"] == 6 and big.adjustments.get("standing", 0) < 0                     # behind the leader: a small drop
    assert abs(big.adjustments.get("standing", 0)) <= config.STANDING_MAX


def test_labels_come_from_people_and_outcomes_win():
    from matcher.schema import Decision
    ds = [Decision(student_id="S1", opp_id="J1", decision="reject", reject_reason="skills gap", created_at="2026-01-01"),
          Decision(student_id="S2", opp_id="J1", decision="accept", created_at="2026-01-01"),
          Decision(student_id="S3", opp_id="J1", decision="accept", what_if=True),
          Decision(student_id="S4", opp_id="J1", decision="flag", note="needs help")]
    apps = [{"student_id": "S1", "opp_id": "J1", "status": "hired"}, {"student_id": "S5", "opp_id": "J1", "status": "not_a_fit"},
            {"student_id": "S6", "opp_id": "J1", "status": "interested"}]
    assert learn.labels(ds, apps) == {("S1", "J1"): 1, ("S2", "J1"): 1, ("S5", "J1"): 0}


def test_model_waits_for_enough_labels_then_learns_coverage():
    s, opps, norm = setup_gap()
    rows, ctx = scored(s, opps, norm)
    job = next(r for r in rows if r.opp_id == "O1")
    by, lab = {}, {}
    for i in range(40):
        cov = i / 39
        by[f"S{i}"] = [job.model_copy(update={"student_id": f"S{i}", "coverage": cov, "skill_sim": cov})]
        lab[(f"S{i}", "O1")] = int(cov > 0.5)
    few = dict(list(lab.items())[:10])
    assert learn.train(by, few) is None
    model = learn.train(by, lab)
    assert model is not None and model.n == 40
    hi, lo = by["S39"][0], by["S0"][0]
    assert model.chance(hi) > 0.8 > 0.2 > model.chance(lo)
    ctx.model = model
    nudged = learn.apply([hi, lo], ctx)
    assert nudged[0].adjustments["ml"] > 0 > nudged[1].adjustments["ml"] and nudged[0].ml > 0.8
    assert abs(nudged[0].adjustments["ml"]) <= config.ML_MAX
    d = learn.describe(model, lab)
    assert d["trained"] and d["learned"][0]["effect"] in ("helps", "hurts") and d["weight"] == 0.4


def test_next_batch():
    o = make_opp(type="training", starts_on="2026-01-05", batch_every_weeks=4)
    assert learning_plan.next_batch(o, date(2026, 1, 1)) == date(2026, 1, 5)
    assert learning_plan.next_batch(o, date(2026, 1, 6)) == date(2026, 2, 2)                     # the next batch, 4 weeks on
    assert learning_plan.next_batch(make_opp(type="training", starts_on="2026-01-05"), date(2026, 3, 1)) is None
    assert learning_plan.next_batch(make_opp(type="mentor"), date(2026, 3, 1)) == date(2026, 3, 1)


def test_plan_picks_a_course_and_shows_the_lift():
    s, opps, norm = setup_gap()
    rows, ctx = scored(s, opps, norm)
    by_id = {o.opp_id: o for o in opps}

    def rescore(skills, ids):
        ns = {**norm, "students": {"X1": {"skills": skills}}}
        again = score_student(s, opps, ns, get_encoder(), ctx=ctx)
        return {r.opp_id: r.final_score for r in again if r.opp_id in ids}
    p = learning_plan.plan(rows, norm, ctx, by_id, ["Excel", "SQL"], rescore, today=date(2026, 1, 1))
    assert [x["opp_id"] for x in p["steps"]] == ["T1"] and p["steps"][0]["teaches"] == ["Python"]
    assert p["steps"][0]["starts_on"] == "2026-01-05" and p["steps"][0]["ends_on"] == "2026-02-02"
    lift = p["steps"][0]["unlocks"][0]
    assert lift["opp_id"] == "O1" and lift["after"] > lift["before"]
    assert p["targets"][0]["after"] > p["targets"][0]["before"] and "Power BI" in p["still_missing"]
    assert p["targets"][0]["before"] == next(r.final_score for r in rows if r.opp_id == "O1")   # agrees with the match card


def test_live_api_has_standing_plans_and_scoring(make_client):
    staff, stud = make_client("staff1"), make_client("stud2")
    ms = staff.get("/api/students/S002/matches").json()["matches"]
    jobs = [m for m in ms if m["type"] == "job"]
    assert jobs and all(m["standing"]["of"] >= m["standing"]["rank"] >= 1 for m in jobs)
    assert "standing" in jobs[0]["breakdown"]
    plan = staff.get("/api/students/S002/plan").json()
    assert set(plan) >= {"targets", "steps", "gap", "message"}
    for sid in ("S001", "S002", "S003", "S010"):                      # learning something never makes a job fit worse
        p = staff.get(f"/api/students/{sid}/plan").json()
        assert all(t["after"] >= t["before"] for t in p["targets"]), sid
        assert all(u["after"] > u["before"] for st in p["steps"] for u in st["unlocks"]), sid
    assert stud.get("/api/me/plan").json()["message"] == plan["message"]
    sc = staff.get("/api/scoring").json()
    assert sc["ml"]["trained"] is False and sc["ml"]["needed"] == config.ML_MIN_LABELS and sc["v3"]["standing"] is True
    assert stud.get("/api/scoring").status_code == 403


@pytest.mark.parametrize("flag", ["upskill", "ml", "standing"])
def test_every_v3_term_can_be_switched_off(flag):
    s, opps, norm = setup_gap()
    ctx = Context.build(opps, norm)
    ctx.v3[flag] = False
    ctx.competition = {"O1": [0.1, 0.2, 0.3, 0.4, 0.5, 0.9]}
    rows = score_student(s, opps, norm, get_encoder(), ctx=ctx)
    assert flag not in next(r for r in rows if r.opp_id == "O1").adjustments


def test_ease_rewards_a_close_skill_and_a_short_cheap_course():
    course = {"type": "training", "cost": 0, "weeks": 4, "budget": 5000}
    assert upskill.ease(0, None) == 0                                                         # nothing to build on
    assert upskill.ease(0.45, None) > upskill.ease(0.2, None) > 0                             # a close relative beats the same area
    assert upskill.ease(0.2, course) > max(upskill.ease(0.2, None), upskill.ease(0, course))  # both together help more
    assert upskill.ease(0, course) > upskill.ease(0, {**course, "type": "mentor"})            # a course teaches, a mentor guides
    assert upskill.ease(0, course) > upskill.ease(0, {**course, "weeks": 12})                 # shorter is easier
    assert upskill.ease(0, course) > upskill.ease(0, {**course, "cost": 4000})                # free is easier
    assert upskill.ease(0, {**course, "cost": 4000, "budget": None}) > 0                      # an unknown budget still counts
    for c in (0, 0.2, 0.49):
        for t in (None, course, {**course, "type": "mentor", "weeks": None, "cost": 9000, "budget": 1000}):
            assert 0 <= upskill.ease(c, t) <= 1


def test_a_learning_plan_prefers_a_course_on_the_schedule_over_a_mentor():
    job = make_opp(opp_id="J1", required_skills_raw=["SQL", "Power BI", "Python"], mode="remote", city="Remote")
    mentor = make_opp(opp_id="M1", type="mentor", title="Mentor", required_skills_raw=["Power BI", "Python"], mode="remote", city="Remote", upfront_cost=0)
    course = make_opp(opp_id="T1", type="training", title="Course", required_skills_raw=["Python"], mode="remote", city="Remote", upfront_cost=0,
                      starts_on="2099-01-05", duration_weeks=4)
    s = make_student(skills_raw=["SQL"], can_relocate=True, budget=5000)
    norm = {"students": {"X1": {"skills": ["SQL"]}},
            "opportunities": {"J1": {"skills": ["SQL", "Power BI", "Python"], "nice": []}, "M1": {"skills": ["Power BI", "Python"], "nice": []},
                              "T1": {"skills": ["Python"], "nice": []}}}
    rows, ctx = scored(s, [job, mentor, course], norm)
    opps = {o.opp_id: o for o in (job, mentor, course)}
    out = learning_plan.plan(rows, norm, ctx, opps, ["SQL"], lambda skills, ids: {i: 0.5 for i in ids}, today=date(2098, 12, 1))
    picked = {x["opp_id"]: x for x in out["steps"]}
    assert picked["T1"]["teaches"] == ["Python"] and picked["T1"]["starts_on"] == "2099-01-05"   # the course takes what it can teach
    assert picked["M1"]["teaches"] == ["Power BI"]                                               # the mentor fills only the rest


def test_a_plan_says_how_long_each_step_and_the_whole_plan_takes():
    job = make_opp(opp_id="J1", required_skills_raw=["SQL", "Power BI", "Python"], mode="remote", city="Remote")
    mentor = make_opp(opp_id="M1", type="mentor", title="Mentor", required_skills_raw=["Power BI"], mode="remote", city="Remote",
                      upfront_cost=0, hours_per_week=2)
    course = make_opp(opp_id="T1", type="training", title="Course", required_skills_raw=["Python"], mode="remote", city="Remote",
                      upfront_cost=0, starts_on="2099-01-05", duration_weeks=4, hours_per_week=8)
    s = make_student(skills_raw=["SQL"], can_relocate=True, budget=5000)
    norm = {"students": {"X1": {"skills": ["SQL"]}},
            "opportunities": {"J1": {"skills": ["SQL", "Power BI", "Python"], "nice": []}, "M1": {"skills": ["Power BI"], "nice": []},
                              "T1": {"skills": ["Python"], "nice": []}}}
    rows, ctx = scored(s, [job, mentor, course], norm)
    opps = {o.opp_id: o for o in (job, mentor, course)}
    out = learning_plan.plan(rows, norm, ctx, opps, ["SQL"], lambda skills, ids: {i: 0.5 for i in ids}, today=date(2098, 12, 1))
    by = {x["opp_id"]: x for x in out["steps"]}
    assert by["T1"]["weeks"] == 4 and by["T1"]["hours_per_week"] == 8 and by["T1"]["total_hours"] == 32 and not by["T1"]["self_paced"]
    assert by["M1"]["self_paced"] and by["M1"]["total_hours"] is None and by["M1"]["hours_per_week"] == 2
    assert out["finish_by"] == "2099-02-02" and out["weeks_total"] == 9 and out["hours_total"] == 32 and out["open_ended"] == 1


def test_a_student_can_pick_their_own_courses_and_only_the_preview_moves(make_client):
    stud, staff, other = make_client("stud2"), make_client("staff1"), make_client("stud1")
    base = stud.get("/api/me/plan").json()
    assert base["custom"] is False and set(base["suggested"]) == {s["opp_id"] for s in base["steps"]}
    opts = [o["opp_id"] for o in base["options"]]
    assert opts, "S002 should have courses that close a gap"
    real = [(m["opp_id"], m["final_score"]) for m in stud.get("/api/me/student").json()["matches"]]

    pick = opts[-1:]                                                               # one of the courses not suggested first
    prev = stud.post("/api/me/plan/preview", json={"opp_ids": pick}).json()
    assert prev["custom"] and [s["opp_id"] for s in prev["steps"]] == pick
    assert stud.get("/api/me/plan").json()["custom"] is False                       # a preview saves nothing
    assert all(t["after"] >= t["before"] for t in prev["targets"])

    assert stud.post("/api/me/plan/preview", json={"opp_ids": ["J028"]}).status_code == 422          # a job is not a course
    assert stud.post("/api/me/plan/preview", json={"opp_ids": ["X"] * 7}).status_code == 422          # at most six
    assert stud.put("/api/me/plan/choices", json={"opp_ids": pick, "extra": 1}).status_code == 422

    saved = stud.put("/api/me/plan/choices", json={"opp_ids": pick}).json()
    assert saved["custom"] and [s["opp_id"] for s in saved["steps"]] == pick
    assert next(o for o in saved["options"] if o["opp_id"] == pick[0])["chosen"]
    assert staff.get("/api/students/S002/plan").json()["custom"] is True                # staff see the student's own plan
    assert other.get("/api/me/plan").json()["custom"] is False                          # nobody else's plan changed
    assert [(m["opp_id"], m["final_score"]) for m in stud.get("/api/me/student").json()["matches"]] == real   # matches untouched

    back = stud.delete("/api/me/plan/choices").json()
    assert back["custom"] is False and back["suggested"] == base["suggested"]
    assert staff.post("/api/me/plan/preview", json={"opp_ids": pick}).status_code == 403


def three_mentors():
    """Kiruba's example: three mentors of different lengths, each teaching what one role lacks."""
    today = date(2099, 1, 1)
    jobs = [make_opp(opp_id="J1", title="Python Role", mode="remote", city="Remote", apply_by="2099-02-20"),
            make_opp(opp_id="J2", title="BI Role", mode="remote", city="Remote", apply_by="2099-02-01"),
            make_opp(opp_id="J3", title="QA Role", mode="remote", city="Remote"),
            make_opp(opp_id="J4", title="Ops Role", mode="remote", city="Remote", apply_by="2099-01-10")]
    mentor = lambda oid, weeks: make_opp(opp_id=oid, type="mentor", title=oid, mode="remote", city="Remote", upfront_cost=0,  # noqa: E731
                                         pay_min=None, pay_max=None, hours_per_week=2, duration_weeks=weeks)
    ms = [mentor("M1", 6), mentor("M2", 4), mentor("M3", 5)]
    norm = {"students": {"X1": {"skills": ["SQL"]}},
            "opportunities": {"J1": {"skills": ["SQL", "Python"], "nice": []}, "J2": {"skills": ["SQL", "Power BI"], "nice": []},
                              "J3": {"skills": ["SQL", "Selenium"], "nice": []}, "J4": {"skills": ["SQL", "Docker"], "nice": []},
                              "M1": {"skills": ["Python"], "nice": []}, "M2": {"skills": ["Power BI"], "nice": []},
                              "M3": {"skills": ["Selenium"], "nice": []}}}
    s = make_student(student_id="X1", skills_raw=["SQL"], can_relocate=True, budget=5000)
    rows, ctx = scored(s, jobs + ms, norm)
    opps = {o.opp_id: o for o in jobs + ms}
    return lambda chosen: learning_plan.plan(rows, norm, ctx, opps, ["SQL"], lambda sk, ids: {i: 0.5 for i in ids},
                                             today=today, chosen=chosen)


def test_picks_run_one_after_another_and_each_role_is_checked_against_its_own_deadline():
    plan = three_mentors()
    p = plan(["M1", "M2", "M3"])
    assert p["order"] == ["M1", "M2", "M3"] and [s["opp_id"] for s in p["steps"]] == ["M1", "M2", "M3"]   # the student's order
    assert [(s["starts_on"], s["ends_on"]) for s in p["steps"]] == [
        ("2099-01-01", "2099-02-12"), ("2099-02-12", "2099-03-12"), ("2099-03-12", "2099-04-16")]          # 6, 4 and 5 weeks in a row
    assert p["finish_by"] == "2099-04-16" and p["weeks_total"] == 15 and p["hours_total"] == 30
    roles = {r["opp_id"]: r for r in p["roles"]}
    assert roles["J1"]["status"] == "in_time" and roles["J1"]["ready_by"] == "2099-02-12"     # only M1 counts for it
    assert roles["J2"]["status"] == "late" and roles["J2"]["ready_by"] == "2099-03-12" and roles["J2"]["days_late"] == 39
    assert roles["J3"]["status"] == "no_deadline" and roles["J4"]["status"] == "not_helped"
    assert p["late"] == 1
    fixes = [(f["kind"], f["opp_id"], f["ready_by"]) for f in p["fixes"] if f["role_id"] == "J2"]
    assert fixes == [("move", "M2", "2099-01-29"), ("drop", "M1", "2099-01-29")]                # both really make it in time
    drop = next(f for f in p["fixes"] if f["kind"] == "drop")
    assert drop["loses"] == ["Python Role"]                                                 # says what dropping M1 gives up

    one = plan(["M2"])                                                                         # one mentor: only its role moves
    r1 = {r["opp_id"]: r for r in one["roles"]}
    assert r1["J2"]["status"] == "in_time" and r1["J1"]["status"] == "not_helped" and one["late"] == 0 and one["fixes"] == []


def test_a_course_after_a_mentor_waits_for_its_next_batch():
    from matcher.learning_plan import schedule
    course = make_opp(opp_id="T1", type="training", starts_on="2099-01-05", duration_weeks=4, batch_every_weeks=4)
    mentor = make_opp(opp_id="M1", type="mentor", duration_weeks=6)
    one_off = make_opp(opp_id="T2", type="training", starts_on="2099-01-05", duration_weeks=2)
    picks = [(None, mentor, None, []), (None, course, None, []), (None, one_off, None, [])]
    got = schedule(picks, date(2099, 1, 1))
    assert got[0] == (date(2099, 1, 1), date(2099, 2, 12))
    assert got[1] == (date(2099, 3, 2), date(2099, 3, 30))           # 5 Jan, 2 Feb have started already: the 2 Mar batch
    assert got[2] == (None, None)                                    # a one-off batch that is over by then


def test_the_suggested_plan_helps_the_nearest_deadline_first():
    p = three_mentors()(None)
    order = p["order"]
    assert order.index("M2") < order.index("M1")                   # BI Role closes first, so its mentor comes first


def test_the_student_order_is_kept_through_preview_save_and_reload(make_client):
    stud = make_client("stud2")
    opts = [o["opp_id"] for o in stud.get("/api/me/plan").json()["options"]]
    if len(opts) < 2:
        pytest.skip("S002 needs two options for this check")
    want = [opts[1], opts[0]]                                                         # the reverse of how they are listed
    prev = stud.post("/api/me/plan/preview", json={"opp_ids": want}).json()
    assert prev["order"] == want and [s["opp_id"] for s in prev["steps"]] == want
    assert {"roles", "fixes", "late", "finish_by"} <= prev.keys()
    assert all({"ready_by", "apply_by", "status"} <= r.keys() for r in prev["roles"])
    stud.put("/api/me/plan/choices", json={"opp_ids": want})
    assert stud.get("/api/me/plan").json()["order"] == want
    stud.delete("/api/me/plan/choices")
