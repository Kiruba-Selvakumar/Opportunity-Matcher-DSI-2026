"""Stored resumes, bulk upload, the viewer and ATS scores. Employers never get a resume."""
import json

from matcher import ats, resumes

from .test_api import make_pdf
from .test_listings_api import GOOD

GOOD_CV = ["Ravi K. ravi@example.com 9876543210", "github.com/ravik", "Summary", "Final year CSE student who builds data tools.",
           "Education", "B.Tech CSE, CGPA 8.1", "Skills", "Python, SQL, Excel, Power BI, Git, Pandas", "Projects",
           "- Built a sales dashboard in Power BI used by 40 shopkeepers, cut report time by 60%",
           "- Developed a Python script that cleaned 20000 rows of survey data", "- Designed and tested a small Django app",
           "Internship", "- Analysed attendance data for 300 students at a local school", "Certifications", "NPTEL Python for Data Science"]


def test_quality_finds_sections_and_gives_tips():
    rich = ats.quality("\n".join(GOOD_CV * 3), 1)
    assert {"education", "skills", "projects", "experience", "certifications", "summary"} <= set(rich["sections"])
    assert rich["has_email"] and rich["has_phone"] and rich["links"]["github"] and rich["results"] >= 3
    assert {"Python", "SQL", "Excel", "Power BI"} <= set(rich["skills"])
    thin = ats.quality("Ravi\nI know python and some sql.", 1)
    assert thin["score"] < rich["score"] and thin["grade"] == "Weak" and len(thin["tips"]) >= 4
    blob = json.dumps(rich)
    assert "ravi@example.com" not in blob and "9876543210" not in blob                      # the report holds no contact details


def test_listing_score_counts_the_listing_skills():
    rep = ats.quality("\n".join(GOOD_CV), 1)
    hit = ats.for_listing(rep, ["Excel", "SQL", "Power BI"], ["Power BI"])
    miss = ats.for_listing(rep, ["Java", "Spring Boot", "SQL"])
    assert hit["coverage"] == 1.0 and hit["keywords_missing"] == [] and hit["score"] > miss["score"]
    assert miss["keywords_missing"] == ["Java", "Spring Boot"] and "Java" in miss["tips"][0]


def test_match_filenames():
    names = {"S001": "Lakshmi Prasanna", "S002": "Ravi Teja", "S003": "Ravi Teja"}
    got = resumes.match_filenames(["S001_resume.pdf", "cv-abcd1234.pdf", "Lakshmi_Prasanna_CV.pdf", "Ravi Teja.pdf", "unknown.pdf"],
                                  ["S001", "S002", "S003"], {"abcd1234": "S002"}, names)
    assert [(g["student_id"], g["how"]) for g in got] == [("S001", "id"), ("S002", "code"), ("S001", "name"), (None, "ambiguous"), (None, None)]
    assert got[3]["options"] == ["S002", "S003"]


def test_save_text_and_delete(pipeline_dir):
    m = resumes.save("S005", make_pdf(GOOD_CV), "ngo", "staff1")
    assert m["quality"] > 50 and m["source"] == "ngo" and resumes.file_for("S005").exists()
    assert "Power BI" in resumes.text("S005")
    assert str(resumes.file_for("S005")).endswith("data/private/resumes/S005.pdf")
    assert resumes.delete("S005") and resumes.meta("S005") is None and not resumes.file_for("S005").exists()


def test_ngo_upload_view_and_ats(make_client):
    staff, admin, acme, stud = make_client("staff1"), make_client("admin1"), make_client("acme"), make_client("stud1")
    r = staff.post("/api/students/S001/resume", files={"file": ("cv.pdf", make_pdf(GOOD_CV), "application/pdf")})
    assert r.status_code == 200, r.text
    assert r.json()["score"] > 50 and "Power BI" in r.json()["not_in_profile"]
    pdf = staff.get("/api/students/S001/resume.pdf")
    assert pdf.status_code == 200 and pdf.headers["content-type"] == "application/pdf"
    assert pdf.headers["x-frame-options"] == "SAMEORIGIN" and "frame-ancestors 'self'" in pdf.headers["content-security-policy"]
    assert staff.get("/api/students/S001").headers["x-frame-options"] == "DENY"                # only the PDF may sit in a frame
    a = staff.get("/api/students/S001/resume/ats?opp_id=J028").json()
    assert 0 <= a["score"] <= 100 and set(a) >= {"keywords_found", "keywords_missing", "tips"}
    matches = staff.get("/api/students/S001/matches").json()["matches"]
    assert all(m["ats"] is not None for m in matches)
    listed = next(s for s in staff.get("/api/students").json() if s["id"] == "S001")
    assert listed["has_resume"] and listed["resume_score"] == r.json()["score"]
    for c in (acme, stud):
        assert c.get("/api/students/S001/resume.pdf").status_code == 403
    assert "resume.view" in [e["action"] for e in admin.get("/api/admin/audit?action=resume.view").json()]
    assert staff.delete("/api/students/S001/resume").status_code == 403                        # deleting is the admin's call
    bad = staff.post("/api/students/S001/resume", files={"file": ("x.pdf", b"not a pdf", "application/pdf")})
    assert bad.status_code == 422 and "not a PDF" in bad.json()["detail"]


def test_bulk_upload_two_steps(make_client):
    staff = make_client("staff1")
    names = ["S007 resume.pdf", "S008.pdf", "nobody.pdf"]
    plan = staff.post("/api/resumes/match", json={"filenames": names}).json()
    assert [p["student_id"] for p in plan] == ["S007", "S008", None]
    files = [("files", (n, make_pdf(GOOD_CV if n != "S008.pdf" else []), "application/pdf")) for n in names]
    r = staff.post("/api/resumes/bulk", files=files, data={"mapping": json.dumps({"S007 resume.pdf": "S007", "S008.pdf": "S008"})})
    assert r.status_code == 200, r.text
    res = {x["file"]: x for x in r.json()["results"]}
    assert r.json()["saved"] == 1 and res["S007 resume.pdf"]["ok"]
    assert not res["S008.pdf"]["ok"] and "no readable text" in res["S008.pdf"]["message"]
    assert not res["nobody.pdf"]["ok"] and res["nobody.pdf"]["message"].startswith("Skipped")
    assert staff.post("/api/resumes/bulk", files=files[:1], data={"mapping": "{not json"}).status_code == 422
    assert "S007" in staff.get("/api/resumes").json()


def test_a_student_keeps_their_resume_and_sees_tips(make_client):
    stud, staff = make_client("stud2"), make_client("staff1")
    r = stud.post("/api/me/resume?keep=true", files={"file": ("me.pdf", make_pdf(GOOD_CV), "application/pdf")})
    assert r.status_code == 200 and r.json()["resume"]["score"] > 50
    mine = stud.get("/api/me/resume").json()
    assert mine["grade"] in ("Strong", "Fair", "Weak") and isinstance(mine["tips"], list)
    assert stud.get("/api/me/resume.pdf").status_code == 200
    assert staff.get("/api/students/S002/resume").json()["source"] == "student"
    assert stud.get("/api/students/S002/resume.pdf").status_code == 403                        # only through /api/me


def test_the_admin_sees_the_resume_beside_the_listing_before_sharing(make_client):
    admin, acme, stud = make_client("admin1"), make_client("acme"), make_client("pupil6")
    oid = admin.post("/api/listings", json={**GOOD, "title": "Side By Side Analyst", "owner_username": "acme"}).json()["opp_id"]
    admin.post("/api/students/S006/resume", files={"file": ("cv.pdf", make_pdf(GOOD_CV), "application/pdf")})
    app = stud.post("/api/me/applications", json={"opp_id": oid}).json()
    rv = admin.get(f"/api/applications/{app['id']}/review").json()
    assert rv["listing"]["title"] == "Side By Side Analyst" and rv["ats"]["score"] > 0 and rv["student"]["resume"]["score"] > 0
    assert rv["application"]["has_resume"] and rv["match"]["checks"]["location"]["status"] == "pass"
    seen = acme.get(f"/api/me/listings/{oid}").json()
    assert "resume" not in json.dumps(seen)
