import json
import os
from pathlib import Path

import pytest

os.environ["LLM_PROVIDER"] = "none"
os.environ["EMBEDDINGS"] = "tfidf"
os.environ["OUTBOX_SYNC"] = "1"          # emails and WhatsApp messages are recorded inside the request, never on a thread
os.environ["MATCHER_DOTENV"] = "0"       # never read .env in tests: real keys there must not send real messages

from matcher import config  # noqa: E402
from matcher.schema import Opportunity, Student  # noqa: E402

FIX = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="session")
def students_small():
    return [Student(**d) for d in json.loads((FIX / "students_small.json").read_text())]


@pytest.fixture(scope="session")
def opps_small():
    return [Opportunity(**d) for d in json.loads((FIX / "opportunities_small.json").read_text())]


@pytest.fixture(scope="session")
def norm_small():
    return json.loads((FIX / "normalized_small.json").read_text())


@pytest.fixture(scope="session")
def pipeline_dir(tmp_path_factory):
    """Run the whole pipeline once into a temp folder (no LLM, TF-IDF vectors)."""
    from matcher import pipeline
    root = tmp_path_factory.mktemp("run")
    old = dict(config.PATHS)
    config.set_roots(root / "data", root / "eval")
    pipeline.run(quiet=True, no_llm=True)
    yield root
    config.PATHS.clear()
    config.PATHS.update(old)


def make_student(**kw):
    base = dict(student_id="X1", branch="CSE", college_town="Khammam", grad_year=2026, cgpa=7.0, backlogs=0,
                skills_raw=[], projects=0, english_level="intermediate", languages=["Telugu", "English"],
                can_relocate=True, budget=5000, family_limits=[], missing_fields=[], parse_method="rule")
    base.update(kw)
    return Student(**base)


def make_opp(**kw):
    base = dict(opp_id="O1", type="job", title="Test", org_name="Org", job_family="Test", required_skills_raw=[],
                city="Hyderabad", mode="onsite", pay_min=360000, pay_max=360000, upfront_cost=0,
                hours_per_week=40, night_shift=False, safety_score=4, languages_required=["English"],
                missing_fields=[], parse_method="rule")
    base.update(kw)
    return Opportunity(**base)


PASSWORD = "a long test password"


@pytest.fixture(scope="session")
def accounts_seeded(pipeline_dir):
    """Accounts for every role, in the temp database of the pipeline run."""
    from matcher import accounts
    spec = [("admin1", "ngo_admin", {}), ("staff1", "ngo_staff", {}), ("stud1", "student", {"student_id": "S001"}),
            ("stud2", "student", {"student_id": "S002"}), ("pupil4", "student", {"student_id": "S004"}),
            ("pupil5", "student", {"student_id": "S005"}), ("pupil6", "student", {"student_id": "S006"}),
            ("acme", "employer", {"listings": ["J028"]}),
            ("other", "employer", {"listings": ["J027"]})]
    for username, role, kw in spec:
        accounts.create_user(username, username.title(), role, password=PASSWORD, must_change=False, **kw)
    return True


@pytest.fixture
def make_client(accounts_seeded):
    """make_client("staff1") returns a signed-in test client. make_client() returns a signed-out one."""
    from fastapi.testclient import TestClient

    from api import deps, server
    from matcher import auth
    deps.reset_state()
    auth.ip_reset()

    def make(username: str | None = None, password: str = PASSWORD, raise_exceptions: bool = True):
        c = TestClient(server.app, raise_server_exceptions=raise_exceptions)
        if username:
            r = c.post("/api/auth/login", json={"username": username, "password": password})
            assert r.status_code == 200, r.text
            c.headers["X-CSRF-Token"] = r.json()["csrf"]
        return c
    return make
