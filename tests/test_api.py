"""NGO staff features of the API, tested as a signed-in staff account."""
import io

import pytest

from api import helpers


def make_pdf(lines: list[str]) -> bytes:
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    y = 800
    for ln in lines:
        c.drawString(60, y, ln)
        y -= 18
    c.save()
    return buf.getvalue()


RESUME_LINES = ["Ravi K. ravi@example.com 9876543210", "B.Tech CSE, CGPA: 8.1",
                "Skills: Python, SQL, ReactJS, Git, DSA", "Projects", "- Library app using Django",
                "- Mini project in ML", "Fluent in English"]


@pytest.fixture
def staff(make_client):
    return make_client("staff1")


def test_whatif_changes_s001_top5(pipeline_dir):
    st = helpers.load_state()
    default = [m["opp_id"] for m in helpers.default_matches(st, "S001")]
    changed = [m["opp_id"] for m in helpers.whatif_matches(
        st, "S001", {"can_relocate": "yes", "budget": 15000, "family_limits": []})]
    assert default != changed
    assert all(m["mode"] == "remote" or m["city"] == "Khammam" for m in helpers.default_matches(st, "S001"))


def test_why_not_lists_removed_options(pipeline_dir):
    st = helpers.load_state()
    items = helpers.why_not(st, "S001")
    assert items and all(i["fails"] for i in items)


def test_student_endpoints(staff):
    rows = staff.get("/api/students").json()
    assert len(rows) == 100 and {"skills", "cgpa", "missing_fields", "best_match", "candidate_code"} <= set(rows[0])
    body = staff.get("/api/students/S001/matches").json()
    assert 1 <= len(body["matches"]) <= 5 and body["matches"][0]["reason"]
    assert staff.get("/api/students/NOPE").status_code == 404
    w = staff.post("/api/students/S001/whatif", json={"can_relocate": "yes", "budget": 15000, "family_limits": []})
    assert w.status_code == 200 and w.json()["what_if"] is True
    assert staff.get("/api/contacts/S001").json()["name"] == "Lakshmi Prasanna"
    assert staff.get("/api/contacts").json()["S001"] == "Lakshmi Prasanna"


def test_breakdown_config_and_raw(staff):
    m = staff.get("/api/students/S001/matches").json()["matches"][0]
    b = m["breakdown"]
    assert abs(0.6 * b["skill_sim"] + 0.4 * b["coverage"] - b["base_score"]) < 1e-3
    assert staff.get("/api/config").json()["weight_sim"] == 0.6
    raw = staff.get("/api/students/S002/raw").json()
    assert raw["skills_text"].startswith("know basic python") and "name" not in raw and "phone" not in raw


def test_decisions_record_who_decided(staff):
    bad = {"student_id": "S003", "opp_id": "J001", "decision": "flag"}
    assert staff.post("/api/decisions", json=bad).status_code == 422
    ok = staff.post("/api/decisions", json={**bad, "note": "check with parents, call 9876543210"})
    assert ok.status_code == 200
    rows = staff.get("/api/decisions").json()
    assert rows[0]["student_id"] == "S003" and "9876543210" not in rows[0]["note"] and rows[0]["decided_by"] == "staff1"
    assert "flag" in staff.get("/api/decisions.csv").text
    assert staff.post("/api/decisions", json={**bad, "note": "x", "surprise": 1}).status_code == 422  # unknown field
    assert staff.post("/api/decisions", json={**bad, "student_id": "ZZZ", "note": "x"}).status_code == 404


def test_opportunity_views(staff):
    opps = staff.get("/api/opportunities").json()
    assert len(opps) == 50 and "eligible_count" in opps[0]
    d = staff.get(f"/api/opportunities/{opps[0]['opp_id']}").json()
    assert d["total_students"] == 100 and len(d["candidates"]) <= 15
    scores = [c["final_score"] for c in d["candidates"]]
    assert scores == sorted(scores, reverse=True)
    assert all(all(ch["status"] != "fail" for ch in c["checks"].values()) for c in d["candidates"])
    assert staff.get("/api/opportunities/NOPE").status_code == 404


def test_pdf_intake_reads_and_matches(staff):
    pdf = make_pdf(RESUME_LINES)
    r = staff.post("/api/intake/pdf", files={"file": ("cv.pdf", pdf, "application/pdf")},
                   data={"branch": "CSE", "college_town": "Khammam", "can_relocate": "no", "budget": "3000"})
    assert r.status_code == 200, r.text
    d = r.json()
    assert {"Python", "SQL", "React", "Git", "Django", "Machine Learning"} <= set(d["skills"])
    assert d["extracted"]["cgpa"] == 8.1 and d["student"]["english_level"] == "fluent" and d["pages"] == 1
    assert "9876543210" not in str(d) and "ravi@example.com" not in str(d)
    assert 1 <= len(d["matches"]) <= 5
    assert all(x["mode"] == "remote" or x["city"] == "Khammam" for x in d["matches"])


def test_pdf_intake_rejects_non_pdf_and_text_endpoints_are_gone(staff):
    bad = staff.post("/api/intake/pdf", files={"file": ("cv.txt", b"Python SQL", "text/plain")})
    assert bad.status_code == 422 and "not a PDF" in bad.json()["detail"]
    assert staff.post("/api/intake/match", json={"resume_text": "Python"}).status_code in (404, 405)
    assert staff.post("/api/intake/parse", json={"resume_text": "Python"}).status_code in (404, 405)


def test_a_staff_decision_reaches_the_learned_score_without_a_restart(make_client):
    from api import deps
    staff = make_client("staff1")
    before = staff.get("/api/scoring").json()["ml"]["labels"]
    st = deps.state()
    oid = next(r.opp_id for r in st.rows_by_student["S040"] if r.type == "job")
    assert staff.post("/api/decisions", json={"student_id": "S040", "opp_id": oid, "decision": "accept"}).status_code == 200
    assert staff.get("/api/scoring").json()["ml"]["labels"] == before + 1


def test_sample_outcomes_train_the_learned_score_and_are_marked(make_client):
    from api import deps
    from matcher import accounts, db, store
    assert accounts.main(["seed-outcomes"]) == 0
    assert accounts.main(["seed-outcomes"]) == 0                                                  # running it twice adds nothing
    made = [d for d in db.list_decisions() if d.decided_by == "sample"]
    assert len(made) == 30 and sum(d.decision == "accept" for d in made) == 15
    deps.reset_state()
    ml = make_client("staff1").get("/api/scoring").json()["ml"]
    assert ml["trained"] is True and ml["labels"] >= 30
    conn = store.connect()                                                                    # later tests must not learn from these
    conn.execute("DELETE FROM decisions WHERE decided_by = 'sample'")
    conn.close()
    deps.reset_state()
