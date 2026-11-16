from datetime import date, timedelta

import pytest
from pydantic import ValidationError

from matcher import casework, db as decisions, profile_edits as pe
from matcher.schema import Decision

from .conftest import make_student


@pytest.fixture
def dbp(tmp_path):
    return tmp_path / "t.db"


def test_edits_are_partial_validated_and_layered(dbp):
    s = make_student(student_id="S001", can_relocate=False, budget=3000, family_limits=["near_home_only"],
                     missing_fields=["english_level"], english_level=None)
    pe.save_edits("S001", pe.ProfileEdit(can_relocate="yes", family_limits=[]), user_id=7, path=dbp)
    pe.save_edits("S001", pe.ProfileEdit(budget=15000), path=dbp)         # a second save keeps the first
    e = pe.get_edits("S001", dbp)
    assert e["can_relocate"] == "yes" and e["family_limits"] == [] and e["budget"] == 15000 and "_updated_at" in e
    now = pe.apply_edits(s, e)
    assert now.can_relocate is True and now.budget == 15000 and now.family_limits == []
    assert pe.apply_edits(s, {}) is s
    assert pe.edited_fields(e) == ["can_relocate", "budget", "family_limits"]
    assert s.can_relocate is False                                        # the original is untouched


def test_unknown_answers_are_marked_missing_again():
    s = make_student(can_relocate=True, budget=5000, missing_fields=[])
    out = pe.apply_edits(s, {"can_relocate": "unknown", "budget": None})
    assert out.can_relocate is None and out.budget is None and set(out.missing_fields) == {"can_relocate", "budget"}


def test_edit_validation(dbp):
    with pytest.raises(ValidationError):
        pe.ProfileEdit(can_relocate="maybe")
    with pytest.raises(ValidationError):
        pe.ProfileEdit(budget=-1)
    with pytest.raises(ValidationError):
        pe.ProfileEdit(branch="ECE")                                      # not an editable field
    with pytest.raises(ValueError, match="not in the skill list"):
        pe.save_edits("S001", pe.ProfileEdit(extra_skills=["Underwater Basket Weaving"]), path=dbp)
    with pytest.raises(ValueError, match="Nothing"):
        pe.save_edits("S001", pe.ProfileEdit(), path=dbp)
    ok = pe.save_edits("S001", pe.ProfileEdit(extra_skills=["Python", "Python", "SQL"]), path=dbp)
    assert ok["extra_skills"] == ["Python", "SQL"]


def test_completeness_counts_what_is_held_back():
    from matcher.schema import CheckResult, MatchRow
    def row(loc):
        ok = CheckResult(status="pass")
        return MatchRow(student_id="S", opp_id="J", type="job", title="t", org_name="o", city="c", mode="onsite", skill_sim=0, coverage=0,
                        base_score=0, final_score=0, eligible=True,
                        checks={"location": CheckResult(status=loc), "budget": ok, "language": ok, "family": ok})
    s = make_student(can_relocate=None, budget=None, english_level=None, languages=[], missing_fields=[])
    c = pe.completeness(s, ["Python"], [row("unknown"), row("unknown"), row("pass")])
    by = {i["field"]: i for i in c["items"]}
    assert c["percent"] == 0 and by["can_relocate"]["impact"] == 2 and not by["skills"]["done"]
    full = pe.completeness(make_student(), ["a", "b", "c"], [])
    assert full["percent"] == 100


def test_notes_followups_and_redaction(dbp):
    n = casework.add_note("S001", "officer", "Call Lakshmi on 9876543210 about travel", (date.today() - timedelta(days=1)).isoformat(),
                          known_names=["Lakshmi Prasanna"], path=dbp)
    assert "9876543210" not in n["body"] and "Lakshmi" not in n["body"]
    casework.add_note("S001", "officer", "Later", (date.today() + timedelta(days=5)).isoformat(), path=dbp)
    casework.add_note("S001", "officer", "No date", path=dbp)
    due = casework.due_followups(path=dbp)
    assert [d["id"] for d in due] == [n["id"]]
    assert casework.mark_done(n["id"], dbp) and casework.due_followups(path=dbp) == []
    for bad in ("", "   ", "x" * 2001):
        with pytest.raises(ValueError):
            casework.add_note("S001", "o", bad, path=dbp)
    with pytest.raises(ValueError, match="date"):
        casework.add_note("S001", "o", "hi", "next week", path=dbp)
    assert len(casework.list_notes("S001", dbp)) == 3 and casework.list_notes("S002", dbp) == []


def test_timeline_is_newest_first_and_only_that_student(dbp):
    from matcher import applications as ap, chat
    decisions.save_decision(Decision(student_id="S001", opp_id="J001", decision="accept"), dbp)
    decisions.save_decision(Decision(student_id="S002", opp_id="J001", decision="accept"), dbp)
    a = ap.create("S001", "J001", path=dbp)
    ap.transition(a["id"], "shared", "ngo", path=dbp)
    casework.add_note("S001", "officer", "Spoke to her", path=dbp)
    chat.post_message(chat.Message(thread_type="student", thread_id="S001", sender_role="student", body="Is it remote?"), dbp)
    t = casework.timeline("S001", {"J001": "Data Analyst"}, edited_at="2020-01-01T00:00:00+00:00", path=dbp)
    kinds = [e["kind"] for e in t]
    assert set(kinds) == {"decision", "application", "note", "message", "edit"} and kinds[-1] == "edit"
    assert not any("S002" in e["text"] for e in t) and sum(e["kind"] == "decision" for e in t) == 1
    assert "Staff accepted Data Analyst" in [e["text"] for e in t if e["kind"] == "decision"][0]
