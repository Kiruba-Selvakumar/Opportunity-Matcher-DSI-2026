import numpy as np

from matcher.embed import get_encoder, profile_vector
from matcher.score import base_score, coverage, score_student, skill_scores


def test_identical_profiles_score_one():
    enc = get_encoder()
    v = profile_vector(["Python", "SQL"], enc)
    assert skill_scores(v[None, :], v[None, :])[0, 0] > 0.999


def test_coverage():
    cov, overlap, missing = coverage(["Python", "SQL"], ["Python", "SQL", "Git"])
    assert cov == 0.667 and overlap == ["Python", "SQL"] and missing == ["Git"]
    assert coverage(["Python"], []) == (1.0, [], [])


def test_base_scores_in_range(students_small, opps_small, norm_small):
    enc = get_encoder()
    for s in students_small:
        for r in score_student(s, opps_small, norm_small, enc):
            assert 0 <= r.base_score <= 1 and 0 <= r.final_score <= 1
    assert base_score(1.0, 1.0) == 1.0


def test_zero_profile_has_zero_vector():
    enc = get_encoder()
    assert not np.any(profile_vector([], enc))
