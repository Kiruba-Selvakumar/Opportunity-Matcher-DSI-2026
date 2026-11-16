import re

from matcher.generate_students import generate_students, is_messy_skills_text
from matcher.skills import load_vocab


def test_basic_shape():
    df = generate_students()
    assert len(df) == 100 and df.student_id.is_unique
    assert set(df.branch) == {"CSE", "CSE (AI and ML)", "CSE (Data Science)", "IT", "ECE", "EEE"}


def test_heroes_exact():
    df = generate_students().set_index("student_id")
    s1, s2, s3 = df.loc["S001"], df.loc["S002"], df.loc["S003"]
    assert (s1["name"], s1.branch, s1.college_town) == ("Lakshmi Prasanna", "CSE", "Khammam")
    assert s1.skills_text == "Python, SQL, Git, Excel, English Communication"
    assert (s1.can_relocate_text, s1.budget_text, s1.family_limits_text) == ("no", "3000", "parents want me near home")
    assert s1.languages_text == "Telugu, English"
    assert (s2["name"], s2.branch, s2.college_town) == ("Ravi Teja", "CSE (AI and ML)", "Guntur")
    assert s2.skills_text == "know basic python, did mini project in ml, little bit sql. english ok"
    assert (s2.can_relocate_text, s2.budget_text, s2.family_limits_text) == ("yes", "15000", "none")
    assert s2.languages_text == "Telugu, English, Hindi"
    assert (s3["name"], s3.branch, s3.college_town) == ("Divya Sree", "ECE", "Warangal")
    assert s3.skills_text == "Embedded C, Arduino, IoT, C, MATLAB"
    assert (s3.can_relocate_text, s3.budget_text, s3.family_limits_text) == ("maybe, need to ask parents", "0", "no night shifts")


def test_messy_share():
    df = generate_students()
    vocab = set(load_vocab())
    share = sum(is_messy_skills_text(t, vocab) for t in df.skills_text) / len(df)
    assert 0.27 <= share <= 0.33


def test_deterministic():
    a = generate_students().to_csv(index=False, lineterminator="\n")
    b = generate_students().to_csv(index=False, lineterminator="\n")
    assert a == b


def test_contact_formats():
    df = generate_students()
    assert all(re.fullmatch(r"[6-9]\d{9}", p) for p in df.phone)
    assert all(e.endswith("@example.com") for e in df.email)
