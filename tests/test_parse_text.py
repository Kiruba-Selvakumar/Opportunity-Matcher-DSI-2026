import pytest

from matcher import llm, parse_text
from matcher.privacy import PIIError, assert_no_pii, redact
from matcher.parse_text import parse_student_text, split_skill_phrases


def test_rule_fallback_when_no_provider(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "none")
    r = parse_student_text("know basic python, did mini project in ml, little bit sql. english ok", "ok")
    assert r["parse_method"] == "rule"
    assert r["skills_raw"] == ["python", "ml", "sql"]
    assert r["projects"] == 1 and r["english_level"] == "intermediate"


def test_llm_result_used_when_valid(monkeypatch):
    monkeypatch.setattr(llm, "complete_json",
                        lambda *a, **k: {"skills_raw": ["python", "sql"], "projects": 2, "english_level": "basic"})
    r = parse_student_text("know basic python, did mini project in ml", "")
    assert r["parse_method"] == "llm" and r["skills_raw"] == ["python", "sql"] and r["projects"] == 2


def test_invalid_llm_json_falls_back(monkeypatch):
    monkeypatch.setattr(llm, "complete_json", lambda *a, **k: {"skills_raw": "python", "projects": "x"})
    assert parse_student_text("know basic python", "")["parse_method"] == "rule"


def test_clean_text_skips_llm(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("LLM should not be called for clean text")
    monkeypatch.setattr(llm, "complete_json", boom)
    assert parse_student_text("Python, SQL, Git", "good")["parse_method"] == "rule"


def test_split_keeps_special_names():
    assert split_skill_phrases("C++, Node.js, CI/CD") == ["c++", "node.js", "ci/cd"]
    assert split_skill_phrases("done 2 projects using py + sql. english ok") == ["py", "sql"]


def test_assert_no_pii_raises_on_phone_and_name():
    with pytest.raises(PIIError):
        assert_no_pii('Skill text: "call 9876543210"', [])
    with pytest.raises(PIIError):
        assert_no_pii("Sravani likes python", ["Sravani Reddy"])
    assert_no_pii("python, sql", ["Sravani Reddy"])


def test_provider_blocks_pii_before_call(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    with pytest.raises(PIIError):
        llm.complete_json("sys", "my phone 9876543210", {}, known_names=[])


def test_redact():
    out = redact("Call Sravani on 9876543210 or s@example.com", ["Sravani Reddy"])
    assert "9876543210" not in out and "Sravani" not in out and "example.com" not in out


def test_phone_pattern_only_matches_standalone_numbers():
    from matcher.privacy import PHONE_RE
    for ok in ["9876543210", "call 9876543210.", "+91 9876543210", "+91-9876543210", "(9876543210)"]:
        assert PHONE_RE.search(ok), ok
    for bad in ["1778123456789", "id 19876543210", "12345678901234", "98765432101", "order 5876543210"]:
        assert not PHONE_RE.search(bad), bad
