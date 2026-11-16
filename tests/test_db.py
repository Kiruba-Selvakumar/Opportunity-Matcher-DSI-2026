import pytest
from pydantic import ValidationError

from matcher import db
from matcher.schema import Decision


def test_save_and_list(tmp_path):
    p = tmp_path / "t.db"
    new_id = db.save_decision(Decision(student_id="S001", opp_id="J001", rank=1, final_score=0.8, decision="accept"), p)
    rows = db.list_decisions(path=p)
    assert new_id == 1 and len(rows) == 1 and rows[0].decision == "accept"
    assert db.list_decisions("reject", path=p) == []


def test_flag_needs_note_reject_needs_reason():
    with pytest.raises(ValidationError):
        Decision(student_id="S1", opp_id="J1", decision="flag", note="  ")
    with pytest.raises(ValidationError):
        Decision(student_id="S1", opp_id="J1", decision="reject")


def test_phone_redacted(tmp_path):
    p = tmp_path / "t.db"
    db.save_decision(Decision(student_id="S1", opp_id="J1", decision="flag", note="call 9876543210 please"), p)
    assert "9876543210" not in db.list_decisions(path=p)[0].note


def test_export_csv(tmp_path):
    p = tmp_path / "t.db"
    db.save_decision(Decision(student_id="S1", opp_id="J1", decision="reject", reject_reason="cost"), p)
    out = tmp_path / "o.csv"
    db.export_csv(out, p)
    assert "reject" in out.read_text()
