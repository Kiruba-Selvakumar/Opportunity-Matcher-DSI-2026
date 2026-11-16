from matcher.filters import check_all, is_eligible

from .conftest import make_opp, make_student


def run(student_kw=None, opp_kw=None):
    return check_all(make_student(**(student_kw or {})), make_opp(**(opp_kw or {})))


def status(res):
    return {k: v.status for k, v in res.items()}


def test_1_defaults_count_relocation_cost_in_budget():
    assert status(run()) == {"location": "pass", "budget": "fail", "language": "pass", "family": "pass"}


def test_2_remote_passes_location_and_budget():
    s = status(run(opp_kw=dict(mode="remote", city="Remote")))
    assert s["location"] == "pass" and s["budget"] == "pass"


def test_3_cannot_relocate():
    assert run(dict(can_relocate=False))["location"].status == "fail"


def test_4_relocation_unknown_stays_eligible():
    res = run(dict(can_relocate=None, budget=20000))
    assert res["location"].status == "unknown"
    assert is_eligible(res)


def test_5_near_home_only_fails_even_if_can_relocate():
    assert run(dict(family_limits=["near_home_only"], can_relocate=True))["location"].status == "fail"


def test_6_cost_over_budget_in_own_town():
    res = run(opp_kw=dict(city="Khammam", mode="onsite", upfront_cost=12000))
    assert res["location"].status == "pass" and res["budget"].status == "fail"


def test_7_budget_unknown():
    res = run(dict(budget=None), dict(mode="remote", city="Remote", upfront_cost=2500))
    assert res["budget"].status == "unknown"


def test_8_language_fail():
    assert run(opp_kw=dict(languages_required=["English", "Hindi"]))["language"].status == "fail"


def test_9_night_shift_family_fail():
    assert run(dict(family_limits=["no_night_shift"]), dict(night_shift=True))["family"].status == "fail"


def test_10_safe_workplace_fail():
    assert run(dict(family_limits=["safe_workplace_required"]), dict(safety_score=2))["family"].status == "fail"
