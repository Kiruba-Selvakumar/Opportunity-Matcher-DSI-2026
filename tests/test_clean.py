import json
import re

import pandas as pd
import pytest

from matcher.clean import (parse_budget, parse_cgpa, parse_family_limits, parse_languages, parse_pay,
                           parse_relocate, parse_upfront)
from matcher.config import PATHS
from matcher.parse_text import parse_english
from matcher.schema import Opportunity, Student


@pytest.mark.parametrize("text,expected", [("7.8", 7.8), ("7.8/10", 7.8), ("78%", 8.2), ("8 cgpa", 8.0), ("", None)])
def test_cgpa(text, expected):
    assert parse_cgpa(text) == expected


@pytest.mark.parametrize("text,expected", [("5000", 5000), ("5k", 5000), ("nil", 0), ("no money", 0), ("0", 0),
                                           ("can manage 2-3k", 2000), ("Rs 12,000", 12000), ("", None)])
def test_budget(text, expected):
    assert parse_budget(text) == expected


@pytest.mark.parametrize("text,expected", [("yes", True), ("y", True), ("ok", True), ("no", False), ("n", False),
                                           ("maybe, need to ask parents", None), ("", None)])
def test_relocate(text, expected):
    assert parse_relocate(text) is expected


@pytest.mark.parametrize("text,expected", [("basic", "basic"), ("little", "basic"), ("ok", "intermediate"),
                                           ("good", "intermediate"), ("can manage", "intermediate"),
                                           ("fluent", "fluent"), ("very good", "fluent"), ("", None)])
def test_english(text, expected):
    assert parse_english(text) == expected


def test_languages_and_family():
    assert parse_languages("telugu and little hindi") == ["Telugu", "Hindi"]
    assert parse_family_limits("parents want me near home") == ["near_home_only"]
    assert parse_family_limits("no night shifts") == ["no_night_shift"]
    assert parse_family_limits("need a safe workplace") == ["safe_workplace_required"]
    assert parse_family_limits("none") == [] and parse_family_limits("") == []


@pytest.mark.parametrize("text,expected", [
    ("3.6 LPA", (360000, 360000)), ("3-4 LPA", (300000, 400000)), ("25k/month", (300000, 300000)),
    ("₹ 30,000 per month", (360000, 360000)), ("4,50,000 per annum", (450000, 450000)),
    ("stipend 10k", (120000, 120000)), ("not disclosed", (None, None)), ("", (None, None))])
def test_pay(text, expected):
    assert parse_pay(text) == expected


@pytest.mark.parametrize("text,expected", [("free", 0), ("0", 0), ("Rs 12,000", 12000), ("25k", 25000)])
def test_upfront(text, expected):
    assert parse_upfront(text) == expected


def test_clean_outputs(pipeline_dir):
    students = json.loads(PATHS["students"].read_text())
    opps = json.loads(PATHS["opportunities"].read_text())
    assert len(students) == 100 and len(opps) == 50
    [Student(**d) for d in students]
    [Opportunity(**d) for d in opps]
    contacts = pd.read_csv(PATHS["contacts"], dtype=str)
    assert len(contacts) == 100
    blob = (PATHS["students"].read_text() + PATHS["opportunities"].read_text()
            + PATHS["cleaning_report"].read_text()).lower()
    for name in contacts["name"]:
        for part in name.split():
            assert not re.search(r"\b" + re.escape(part.lower()) + r"\b", blob), part
    assert not re.search(r"[6-9]\d{9}", blob) and "@example.com" not in blob


def test_missing_fields_filled(pipeline_dir):
    raw = pd.read_csv(PATHS["students_raw"], dtype=str, keep_default_na=False).set_index("student_id")
    clean = {d["student_id"]: d for d in json.loads(PATHS["students"].read_text())}
    for sid, row in raw.iterrows():
        if row.cgpa_text == "":
            assert "cgpa" in clean[sid]["missing_fields"] and clean[sid]["cgpa"] is None
        if row.budget_text == "":
            assert "budget" in clean[sid]["missing_fields"]
    assert "can_relocate" in clean["S003"]["missing_fields"]
