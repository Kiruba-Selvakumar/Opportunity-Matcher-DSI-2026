from matcher.embed import get_encoder
from matcher.rank import top_k
from matcher.score import score_student

from .conftest import make_opp  # noqa: F401


def rows_for(sid, students_small, opps_small, norm_small):
    s = next(x for x in students_small if x.student_id == sid)
    return score_student(s, opps_small, norm_small, get_encoder())


def test_at_most_five_and_all_eligible(students_small, opps_small, norm_small):
    for s in students_small:
        picks = top_k(rows_for(s.student_id, students_small, opps_small, norm_small))
        assert len(picks) <= 5 and all(p.eligible for p in picks)


def test_variety_rule(students_small, opps_small, norm_small):
    picks = top_k(rows_for("S004", students_small, opps_small, norm_small))
    from collections import Counter
    assert max(Counter(p.type for p in picks).values()) <= 3


def test_s001_only_remote_or_khammam(students_small, opps_small, norm_small):
    picks = top_k(rows_for("S001", students_small, opps_small, norm_small))
    assert picks
    assert all(p.mode == "remote" or p.city == "Khammam" for p in picks)


def test_sorted_by_score(students_small, opps_small, norm_small):
    picks = top_k(rows_for("S002", students_small, opps_small, norm_small))
    scores = [p.final_score for p in picks]
    assert scores == sorted(scores, reverse=True)
