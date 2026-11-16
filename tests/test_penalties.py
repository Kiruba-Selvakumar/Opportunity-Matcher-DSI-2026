from matcher.penalties import final_score, penalties

from .conftest import make_opp


def test_safety_3_example():
    pens = penalties(make_opp(safety_score=3, hours_per_week=40))
    assert final_score(0.82, pens) == 0.79


def test_boundaries():
    assert penalties(make_opp(hours_per_week=48))["hours"] == 0
    assert penalties(make_opp(hours_per_week=49))["hours"] == 0.05
    assert penalties(make_opp(safety_score=4))["safety"] == 0
    assert penalties(make_opp(safety_score=2))["safety"] == 0.10
    assert final_score(0.05, {"a": 0.1}) == 0
