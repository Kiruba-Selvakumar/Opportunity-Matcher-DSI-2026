import pytest
from pydantic import ValidationError

from matcher.schema import Decision, Opportunity, Student

from .conftest import make_opp, make_student


def test_fixtures_validate(students_small, opps_small):
    assert len(students_small) == 5 and len(opps_small) == 8


def test_fixtures_cover_edge_cases(students_small, opps_small):
    assert any(s.can_relocate is False for s in students_small)
    assert any(s.budget == 0 for s in students_small)
    assert any("no_night_shift" in s.family_limits for s in students_small)
    assert any(o.mode == "remote" for o in opps_small)
    assert any(o.night_shift for o in opps_small)
    assert any(o.type == "training" and o.upfront_cost == 12000 for o in opps_small)


def test_invalid_branch_raises():
    with pytest.raises(ValidationError):
        make_student(branch="MECH")


def test_remote_with_city_raises():
    with pytest.raises(ValidationError):
        make_opp(mode="remote", city="Hyderabad")


def test_decision_rules():
    with pytest.raises(ValidationError):
        Decision(student_id="S1", opp_id="J1", decision="flag")
    with pytest.raises(ValidationError):
        Decision(student_id="S1", opp_id="J1", decision="reject")
    assert Decision(student_id="S1", opp_id="J1", decision="accept").decision == "accept"
