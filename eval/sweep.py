"""Call every API route on a running server as the right person, and check that everyone else is kept out.

    python -m eval.sweep --base http://localhost:8000                     (API started with DEMO_LOGIN=1)
    python -m eval.sweep --base https://your-test-server --password '...' --yes-this-is-a-test-server

It needs the demo accounts (make demo-users) and leaves test listings, applications and messages behind, so run it on a
test database. It will not run if real messages could reach real people: with email or WhatsApp live, set stand-ins first.
A route that needs a real Google or Fireflies account is listed separately, because a dry run cannot prove it works.
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import io
import json
import re
import sys
import time
from datetime import datetime, timedelta

import httpx

ROLES = ("admin", "officer", "s001", "s002", "s003", "gopuram")
NGO = {"admin", "officer"}
EVERYONE = set(ROLES)
SAMPLE_LEAD = "919000000555"


def resume_pdf(lines: list[str]) -> bytes:
    from reportlab.pdfgen import canvas
    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    for i, line in enumerate(lines):
        c.drawString(72, 760 - i * 22, line)
    c.save()
    return buf.getvalue()


class Sweep:
    def __init__(self, base: str, password: str | None, verify_token: str | None = None, app_secret: str | None = None):
        self.base, self.password, self.verify_token, self.app_secret = base.rstrip("/"), password, verify_token, app_secret
        self.clients: dict[str, httpx.Client] = {}
        self.csrf: dict[str, str] = {}
        self.covered: set[tuple[str, str]] = set()
        self.failures: list[str] = []
        self.needs_account: list[str] = []
        self.calls = self.denied = 0

    # ---------- plumbing ----------

    def client(self) -> httpx.Client:
        return httpx.Client(base_url=self.base, timeout=60, follow_redirects=False)

    def sign_in(self, role: str) -> None:
        c = self.client()
        r = (c.post("/api/auth/login", json={"username": role, "password": self.password}) if self.password
             else c.post("/api/auth/demo-login", json={"username": role}))
        if r.status_code != 200:
            raise SystemExit(f"Could not sign in as {role} ({r.status_code}). Run make demo-users first, and pass --password unless the API runs with DEMO_LOGIN=1.")
        self.clients[role], self.csrf[role] = c, r.json()["csrf"]

    def send(self, who: str | None, method: str, path: str, **kw) -> httpx.Response:
        c = self.clients[who] if who else self.anon
        headers = {"X-CSRF-Token": self.csrf[who]} if who else {}
        return c.request(method, path, headers=headers, **kw)

    def call(self, who: str | None, method: str, template: str, path: str | None = None, allowed: set[str] | None = None,
             expect: tuple[int, ...] = (200,), needs_account: bool = False, check=None, **kw) -> httpx.Response:
        """One route as one person. allowed: everyone who may call it. The rest, and a signed-out visitor, are refused first."""
        path = path or template
        self.covered.add((method, template))
        label = f"{method} {template}"
        allowed = {who} if allowed is None and who else (allowed or set())
        if who:
            for other in [None, *sorted(EVERYONE - allowed)]:
                r = self.send(other, method, path, **{k: v for k, v in kw.items() if k != "params"}, params=kw.get("params"))
                self.denied += 1
                if r.status_code not in (401, 403, 404):
                    self.failures.append(f"{label}: {other or 'signed out'} should be refused, got {r.status_code}")
        r = self.send(who, method, path, **kw)
        self.calls += 1
        if r.status_code not in expect:
            self.failures.append(f"{label} as {who or 'visitor'}: expected {expect}, got {r.status_code}: {r.text[:160]}")
        elif check is not None:
            try:
                ok = check(r)
            except Exception as e:  # noqa: BLE001 - a wrong shape is a failure to report, not a crash
                ok, r_text = False, repr(e)
                self.failures.append(f"{label}: the response looks wrong: {r_text[:160]}")
            else:
                if not ok:
                    self.failures.append(f"{label}: the response looks wrong: {r.text[:160]}")
        if needs_account and r.status_code not in (200, 201):
            self.needs_account.append(f"{label} answered {r.status_code} without a real account")
        return r

    def j(self, r: httpx.Response):
        try:
            return r.json()
        except ValueError:
            return {}

    # ---------- the run ----------

    def run(self) -> None:
        self.anon = self.client()
        self.public_routes()
        for role in ROLES:
            self.sign_in(role)
        self.covered |= {("POST", "/api/auth/login"), ("POST", "/api/auth/demo-login")}
        self.safety_check()
        tag = str(int(time.time()))
        try:
            self.accounts(tag)
            self.staff_reads()
            emp_listing, ngo_listing = self.listings(tag)
            self.resumes(ngo_listing)
            app_s002, app_s003 = self.student_side(emp_listing, ngo_listing)
            self.pipeline_and_interviews(emp_listing, app_s002, app_s003)
            self.messages_and_leads(emp_listing, tag)
            self.google_and_close(ngo_listing)
            self.sign_out()
        except (KeyError, TypeError, IndexError, StopIteration, AttributeError) as e:   # a failed step left the next one without its data
            self.failures.append(f"the run stopped early, after the failures above: {type(e).__name__}: {e}")

    def public_routes(self) -> None:
        self.call(None, "GET", "/api/health", check=lambda r: r.json()["ok"] is True)
        self.call(None, "GET", "/api/ready", check=lambda r: r.json()["ready"] is True)
        mode = self.call(None, "GET", "/api/auth/mode").json()
        self.demo = bool(mode.get("demo"))
        self.call(None, "GET", "/api/auth/demo-users", expect=(200,) if self.demo else (404,))
        r = self.anon.post("/api/auth/login", json={"username": "admin", "password": "wrong wrong wrong"})
        if r.status_code != 401:
            self.failures.append(f"a wrong password should get 401, got {r.status_code}")

    def safety_check(self) -> None:
        s = self.send("admin", "GET", "/api/integrations").json()
        if (s["email"]["live"] or s["whatsapp"]["live"]) and not s["test_mode"]["active"]:
            raise SystemExit("Email or WhatsApp is live with no stand-ins, so this could message real people. Set STANDIN_EMAIL and STANDIN_WHATSAPP first.")
        self.google_connected = s["google"]["connected"]
        r = self.clients["admin"].post("/api/notifications/read-all")
        if r.status_code != 403:
            self.failures.append(f"a change without the CSRF token should get 403, got {r.status_code}")

    def accounts(self, tag: str) -> None:
        self.call("admin", "GET", "/api/auth/me", allowed=EVERYONE)
        self.call("admin", "GET", "/api/auth/sessions", allowed=EVERYONE)
        self.call("admin", "GET", "/api/skills", allowed=EVERYONE, check=lambda r: len(r.json()) > 10)
        self.call("admin", "PUT", "/api/auth/email", allowed=EVERYONE, json={"email": "admin@ngo.example.org"}, check=lambda r: r.json()["user"]["email"])
        self.call("admin", "GET", "/api/admin/users", check=lambda r: len(r.json()) >= 6)
        username = f"sweep{tag}"
        made = self.call("admin", "POST", "/api/admin/users", json={"username": username, "display_name": "Sweep Employer", "role": "employer",
                                                                     "listings": [], "email": "sweep@example.com"}).json()
        uid = made["user"]["id"]
        self.call("admin", "PATCH", "/api/admin/users/{user_id}", f"/api/admin/users/{uid}", json={"display_name": "Sweep Employer 2"})
        temp = self.call("admin", "POST", "/api/admin/users/{user_id}/reset-password", f"/api/admin/users/{uid}/reset-password").json()["temporary_password"]
        c = self.client()
        r = c.post("/api/auth/login", json={"username": username, "password": temp})
        if r.status_code != 200:
            self.failures.append(f"POST /api/auth/login with a temporary password: got {r.status_code}")
        self.clients["new"], self.csrf["new"] = c, r.json().get("csrf", "")
        new_password = f"a long new password {tag}"
        self.call("new", "POST", "/api/auth/change-password", allowed=EVERYONE | {"new"}, json={"current": temp, "new": new_password})
        self.call("new", "POST", "/api/auth/sessions/revoke-others", allowed=EVERYONE | {"new"})
        self.call("admin", "PATCH", "/api/admin/users/{user_id}", f"/api/admin/users/{uid}", json={"is_active": False})
        self.call("admin", "GET", "/api/admin/audit", check=lambda r: len(r.json()) > 0)
        self.call("admin", "GET", "/api/admin/audit.csv", check=lambda r: "action" in r.text.splitlines()[0])

    def staff_reads(self) -> None:
        kw = {"allowed": NGO}
        self.call("officer", "GET", "/api/students", check=lambda r: len(r.json()) >= 1, **kw)
        self.call("officer", "GET", "/api/students/{sid}", "/api/students/S001", check=lambda r: r.json()["student_id"] == "S001", **kw)
        self.call("officer", "GET", "/api/students/{sid}/raw", "/api/students/S001/raw", **kw)
        m = self.call("officer", "GET", "/api/students/{sid}/matches", "/api/students/S001/matches", check=lambda r: "why_not" in r.json(), **kw).json()
        self.first_opp = m["matches"][0]["opp_id"]
        self.call("officer", "POST", "/api/students/{sid}/whatif", "/api/students/S001/whatif", json={"can_relocate": "yes", "budget": 15000, "family_limits": []},
                  check=lambda r: r.json()["what_if"] is True, **kw)
        self.call("officer", "GET", "/api/contacts", check=lambda r: "S001" in r.json(), **kw)
        self.call("officer", "GET", "/api/contacts/{sid}", "/api/contacts/S001", **kw)
        self.call("officer", "GET", "/api/config", **kw)
        self.call("officer", "GET", "/api/scoring", check=lambda r: "ml" in r.json(), **kw)
        self.call("officer", "GET", "/api/dashboard", check=lambda r: "attention" in r.json(), **kw)
        self.call("officer", "GET", "/api/students/{sid}/timeline", "/api/students/S001/timeline", **kw)
        self.call("officer", "GET", "/api/students/{sid}/plan", "/api/students/S001/plan", **kw)
        note = self.call("officer", "POST", "/api/students/{sid}/notes", "/api/students/S001/notes",
                         json={"body": "Sweep note: call about travel.", "follow_up_on": datetime.now().strftime("%Y-%m-%d")}, **kw).json()
        self.call("officer", "GET", "/api/students/{sid}/notes", "/api/students/S001/notes", check=lambda r: len(r.json()) > 0, **kw)
        self.call("officer", "GET", "/api/followups", check=lambda r: any(n["id"] == note["id"] for n in r.json()), **kw)
        self.call("officer", "POST", "/api/notes/{note_id}/done", f"/api/notes/{note['id']}/done", **kw)
        self.call("officer", "POST", "/api/decisions", json={"student_id": "S003", "opp_id": self.first_opp, "decision": "flag", "note": "Sweep: check with parents."}, **kw)
        self.call("officer", "GET", "/api/decisions", check=lambda r: len(r.json()) > 0, **kw)
        self.call("officer", "GET", "/api/decisions.csv", check=lambda r: "decision" in r.text.splitlines()[0], **kw)
        self.call("officer", "GET", "/api/opportunities", check=lambda r: len(r.json()) > 0, **kw)
        self.call("officer", "GET", "/api/opportunities/{oid}", f"/api/opportunities/{self.first_opp}", **kw)
        self.call("officer", "GET", "/api/threads", **kw)
        self.call("officer", "GET", "/api/threads/unread", check=lambda r: "unread" in r.json(), **kw)
        self.call("officer", "GET", "/api/applications", **kw)
        self.call("officer", "GET", "/api/interviews", **kw)
        self.call("officer", "GET", "/api/students/{sid}/consent", "/api/students/S001/consent", check=lambda r: "reachable" in r.json(), **kw)
        self.call("officer", "PUT", "/api/students/{sid}/consent", "/api/students/S001/consent", json={"whatsapp": True}, **kw)

    def listings(self, tag: str) -> tuple[str, str]:
        form = {"title": f"Sweep Python Developer {tag}", "org_name": "Gopuram Software", "required_skills_text": "Python, SQL, Excel", "mode": "remote",
                "pay_text": "4 LPA", "hours_per_week": 40, "openings": 2, "description": "A test listing from the endpoint sweep."}
        self.call("gopuram", "GET", "/api/me/listings", check=lambda r: isinstance(r.json(), list))
        oid = self.call("gopuram", "POST", "/api/me/listings", json=form).json()["opp_id"]
        path = f"/api/me/listings/{oid}"
        self.call("gopuram", "GET", "/api/me/listings/{oid}", path, check=lambda r: r.json()["opp_id"] == oid)
        self.call("gopuram", "PUT", "/api/me/listings/{oid}", path, json={**form, "description": "Edited by the endpoint sweep."})
        self.call("gopuram", "POST", "/api/me/listings/{oid}/submit", f"{path}/submit", check=lambda r: r.json()["status"] == "pending")
        self.call("gopuram", "POST", "/api/me/listings/{oid}/copy", f"{path}/copy")
        self.call("officer", "GET", "/api/listings/review", allowed=NGO, check=lambda r: any(x["opp_id"] == oid for x in r.json()))
        review = {"decision": "approve", "safety_score": 4, "note": "Fine.", "tell_students": True}
        self.call("admin", "POST", "/api/listings/{oid}/review", f"/api/listings/{oid}/review", json=review, check=lambda r: r.json()["status"] == "active")
        self.call("gopuram", "POST", "/api/me/listings/{oid}/close", f"{path}/close", check=lambda r: r.json()["status"] == "closed")
        status = self.call("gopuram", "POST", "/api/me/listings/{oid}/reopen", f"{path}/reopen").json().get("status")
        if status == "pending":
            self.send("admin", "POST", f"/api/listings/{oid}/review", json=review)
        ngo_form = {**form, "title": f"Sweep NGO Listing {tag}", "safety_score": 4}
        ngo_oid = self.call("admin", "POST", "/api/listings", json=ngo_form, check=lambda r: r.json()["status"] == "active").json()["opp_id"]
        self.call("admin", "GET", "/api/listings/{oid}/form", f"/api/listings/{ngo_oid}/form", check=lambda r: r.json()["opp_id"] == ngo_oid)
        self.call("admin", "PUT", "/api/listings/{oid}", f"/api/listings/{ngo_oid}", json={**ngo_form, "description": "Edited by the NGO."})
        return oid, ngo_oid

    def resumes(self, oid: str) -> None:
        pdf = resume_pdf(["Sweep Student", "B.Tech CSE, Khammam, 2026", "Skills: Python, SQL, Excel, Git, Django",
                          "Projects: attendance tracker in Django", "Languages: Telugu, English"])
        file = {"file": ("S014_resume.pdf", pdf, "application/pdf")}
        kw = {"allowed": NGO}
        self.call("officer", "POST", "/api/intake/pdf", files=file, check=lambda r: "matches" in r.json(), **kw)
        self.call("officer", "POST", "/api/students/{sid}/resume", "/api/students/S014/resume", files=file, **kw)
        self.call("officer", "GET", "/api/students/{sid}/resume", "/api/students/S014/resume", check=lambda r: r.json() is not None, **kw)
        self.call("officer", "GET", "/api/students/{sid}/resume.pdf", "/api/students/S014/resume.pdf", check=lambda r: r.content.startswith(b"%PDF"), **kw)
        self.call("officer", "GET", "/api/students/{sid}/resume/ats", "/api/students/S014/resume/ats", params={"opp_id": oid}, **kw)
        self.call("officer", "GET", "/api/resumes", check=lambda r: "S014" in r.json(), **kw)
        self.call("officer", "POST", "/api/resumes/match", json={"filenames": ["S015_resume.pdf"]}, check=lambda r: r.json()[0]["student_id"] == "S015", **kw)
        self.call("officer", "POST", "/api/resumes/bulk", data={"mapping": json.dumps({"S015_resume.pdf": "S015"})},
                  files=[("files", ("S015_resume.pdf", pdf, "application/pdf"))], check=lambda r: r.json()["saved"] == 1, **kw)
        self.call("admin", "DELETE", "/api/students/{sid}/resume", "/api/students/S015/resume")
        keep = {"file": ("mine.pdf", pdf, "application/pdf")}
        self.call("s001", "POST", "/api/me/resume", params={"keep": "true"}, files=keep, allowed={"s001", "s002", "s003"}, check=lambda r: r.json()["resume"] is not None)
        self.call("s001", "GET", "/api/me/resume", allowed={"s001", "s002", "s003"})
        self.call("s001", "GET", "/api/me/resume.pdf", allowed={"s001", "s002", "s003"}, expect=(200,), check=lambda r: r.content.startswith(b"%PDF"))

    def student_side(self, oid: str, other: str) -> tuple[int, int]:
        kw = {"allowed": {"s001", "s002", "s003"}}
        self.call("s002", "GET", "/api/me/student", check=lambda r: "matches" in r.json() or isinstance(r.json(), dict), **kw)
        self.call("s002", "GET", "/api/me/profile", check=lambda r: "profile" in r.json(), **kw)
        self.call("s002", "PUT", "/api/me/profile", json={"english_level": "fluent"}, **kw)
        browse = self.call("s002", "GET", "/api/me/browse", check=lambda r: any(x["opp_id"] == oid for x in r.json()), **kw).json()
        if not next((x for x in browse if x["opp_id"] == oid), {}).get("eligible"):
            self.failures.append(f"S002 should be able to take the test listing {oid}")
        self.call("s002", "GET", "/api/me/browse/{oid}", f"/api/me/browse/{oid}",
                  check=lambda r: r.json()["opp_id"] == oid and "apply_by" in r.json() and "skills" in r.json(), **kw)
        plan = self.call("s002", "GET", "/api/me/plan", check=lambda r: "options" in r.json(), **kw).json()
        pick = [o["opp_id"] for o in plan.get("options", [])][:1]
        self.call("s002", "POST", "/api/me/plan/preview", json={"opp_ids": pick}, check=lambda r: r.json()["custom"] is True, **kw)
        self.call("s002", "PUT", "/api/me/plan/choices", json={"opp_ids": pick}, check=lambda r: r.json()["custom"] is True, **kw)
        self.call("s002", "DELETE", "/api/me/plan/choices", check=lambda r: r.json()["custom"] is False, **kw)
        self.call("s002", "GET", "/api/me/contact", check=lambda r: "pending" in r.json(), **kw)
        self.call("s002", "POST", "/api/me/contact-change", json={"phone": "98765 01234"},
                  check=lambda r: r.json()["pending"] is not None and "9876501234" not in r.text, **kw)
        waiting = self.call("officer", "GET", "/api/contact-changes", params={"student_id": "S002"}, allowed=NGO,
                            check=lambda r: len(r.json()) == 1).json()
        if waiting:     # turned down, so a sweep against a demo database never changes anyone's number
            self.call("officer", "POST", "/api/contact-changes/{change_id}/decision", f"/api/contact-changes/{waiting[0]['id']}/decision",
                      json={"approve": False, "note": "sweep"}, allowed=NGO, check=lambda r: r.json()["status"] == "rejected")
        self.call("s002", "GET", "/api/me/consent", **kw)
        self.call("s002", "PUT", "/api/me/consent", json={"whatsapp": True}, check=lambda r: r.json()["whatsapp"] is True, **kw)
        self.call("s002", "PUT", "/api/me/saved/{opp_id}", f"/api/me/saved/{oid}", **kw)
        self.call("s002", "GET", "/api/me/saved", check=lambda r: any(x["opp_id"] == oid for x in r.json()), **kw)
        self.call("s002", "DELETE", "/api/me/saved/{opp_id}", f"/api/me/saved/{oid}", **kw)
        self.call("s002", "GET", "/api/me/export", check=lambda r: "applications" in r.json(), **kw)
        self.call("s002", "GET", "/api/me/export", params={"format": "html"},
                  check=lambda r: r.headers["content-type"].startswith("text/html") and "Your applications" in r.text, **kw)
        a2 = self.call("s002", "POST", "/api/me/applications", json={"opp_id": oid, "note": "I know Python and SQL."}, **kw).json()
        a3 = self.call("s003", "POST", "/api/me/applications", json={"opp_id": oid, "note": "Please consider me."}, **kw).json()
        self.call("s002", "GET", "/api/me/applications", check=lambda r: any(x["opp_id"] == oid for x in r.json()), **kw)
        back = self.send("s002", "POST", "/api/me/applications", json={"opp_id": other}).json()
        withdraw = f"/api/me/applications/{back.get('id')}/withdraw"
        cross = self.send("s003", "POST", withdraw, json={"note": "not mine"})
        if cross.status_code != 404:
            self.failures.append(f"a student withdrew another student's application: {cross.status_code}")
        self.call("s002", "POST", "/api/me/applications/{app_id}/withdraw", withdraw, json={"note": "Changed my mind."}, **kw)
        return a2.get("id"), a3.get("id")

    def pipeline_and_interviews(self, oid: str, a2: int, a3: int) -> None:
        when = (datetime.now() + timedelta(days=3)).replace(minute=0, second=0, microsecond=0).strftime("%Y-%m-%dT%H:%M")
        later = (datetime.now() + timedelta(days=4)).replace(minute=0, second=0, microsecond=0).strftime("%Y-%m-%dT%H:%M")
        kw = {"allowed": NGO}
        self.call("officer", "POST", "/api/applications/{app_id}/recommend", f"/api/applications/{a2}/recommend", json={"note": "Good Python and SQL."}, **kw)
        self.call("admin", "GET", "/api/applications/{app_id}/review", f"/api/applications/{a2}/review", check=lambda r: "ats" in r.json(), **kw)
        status = "/api/applications/{app_id}/status"
        if self.send("officer", "POST", f"/api/applications/{a3}/status", json={"status": "shared", "note": ""}).status_code != 403:
            self.failures.append("staff should not be able to share a student with an employer")
        self.call("admin", "POST", status, f"/api/applications/{a2}/status", allowed=NGO, json={"status": "shared", "note": "Sharing."}, expect=(200,))
        self.send("admin", "POST", f"/api/applications/{a3}/status", json={"status": "shared", "note": "Sharing."})
        self.call("gopuram", "POST", "/api/me/applications/{app_id}/status", f"/api/me/applications/{a2}/status", json={"status": "shortlisted", "note": ""})
        meet = {"starts_at": when, "minutes": 30, "mode": "meet", "meet_link": "https://meet.google.com/abc-defg-hij", "notetaker": False}
        iv = self.call("gopuram", "POST", "/api/me/applications/{app_id}/interviews", f"/api/me/applications/{a2}/interviews", json=meet,
                       check=lambda r: r.json()["interview"]["id"] > 0).json()["interview"]["id"]
        iv2 = self.call("admin", "POST", "/api/applications/{app_id}/interviews", f"/api/applications/{a3}/interviews", allowed=NGO,
                        json={**meet, "meet_link": None, "interviewer": "ngo", "invite_student": True, "notetaker": True},
                        check=lambda r: r.json()["interview"]["meet_link"] or not self.google_connected).json()["interview"]["id"]
        self.call("gopuram", "GET", "/api/me/interviews", check=lambda r: any(x["id"] == iv for x in r.json()))
        ivp = f"/api/interviews/{iv}"
        both = NGO | {"gopuram"}
        self.call("gopuram", "GET", "/api/interviews/{iid}/invite.ics", f"{ivp}/invite.ics", allowed=both, check=lambda r: "BEGIN:VCALENDAR" in r.text)
        self.call("gopuram", "PATCH", "/api/interviews/{iid}", ivp, allowed=both, json={"starts_at": later, "minutes": 45})
        transcript = "Interviewer: Thanks for joining. Ravi will send his marks memo by Friday. The team will share the next steps by Monday."
        self.call("gopuram", "POST", "/api/interviews/{iid}/notes", f"{ivp}/notes", allowed=both, json={"text": transcript}, check=lambda r: r.json()["action_items"])
        self.call("officer", "POST", "/api/interviews/{iid}/to-case-notes", f"{ivp}/to-case-notes", allowed=NGO, json={})
        self.call("officer", "POST", "/api/interviews/{iid}/notetaker", f"{ivp}/notetaker", allowed=NGO, expect=(200, 422), needs_account=True)
        self.call("officer", "POST", "/api/interviews/{iid}/fetch-notes", f"{ivp}/fetch-notes", allowed=NGO, expect=(200, 404, 422), needs_account=True)
        self.call("admin", "PATCH", "/api/interviews/{iid}", f"/api/interviews/{iv2}", allowed=both, json={"status": "cancelled"}, check=lambda r: r.json()["status"] == "cancelled")
        r = self.send(None, "POST", "/api/fireflies/webhook", json={"meetingId": "none"})
        self.covered.add(("POST", "/api/fireflies/webhook"))
        self.needs_account.append(f"POST /api/fireflies/webhook answered {r.status_code} without a real account")
        if r.status_code not in (200, 403, 502):
            self.failures.append(f"POST /api/fireflies/webhook: unexpected {r.status_code}")
        for step in ("offered", "hired"):
            self.send("gopuram", "POST", f"/api/me/applications/{a2}/status", json={"status": step, "note": ""})
        final = next((x for x in self.send("s002", "GET", "/api/me/applications").json() if x["opp_id"] == oid), {})
        if final.get("status") != "hired":
            self.failures.append(f"the student should see hired after the employer hires, got {final.get('status')}")

    def messages_and_leads(self, oid: str, tag: str) -> None:
        thread = "/api/threads/{thread_type}/{thread_id}/messages"
        self.call("s001", "POST", thread, "/api/threads/student/S001/messages", allowed=NGO | {"s001"}, json={"body": "Hello from the sweep."})
        self.call("officer", "GET", thread, "/api/threads/student/S001/messages", allowed=NGO | {"s001"}, check=lambda r: len(r.json()) > 0)
        self.call("gopuram", "POST", thread, f"/api/threads/listing/{oid}/messages", allowed=NGO | {"gopuram"}, json={"body": "A question about this listing."})
        n = self.call("s002", "GET", "/api/notifications", allowed=EVERYONE, check=lambda r: "items" in r.json()).json()["items"]
        if n:
            self.call("s002", "POST", "/api/notifications/{notification_id}/read", f"/api/notifications/{n[0]['id']}/read",
                      allowed={"s002"}, expect=(200,))
        else:
            self.failures.append("S002 should have notifications after the journey")
        self.call("s002", "POST", "/api/notifications/read-all", allowed=EVERYONE)
        self.call("admin", "POST", "/api/broadcasts/preview", json={"kind": "update", "text": "Sweep test update."}, check=lambda r: r.json()["reachable"] >= 1)
        self.call("admin", "POST", "/api/broadcasts", json={"kind": "update", "text": "Sweep test update."}, check=lambda r: r.json()["queued"] >= 1)
        self.call("admin", "GET", "/api/outbox", check=lambda r: len(r.json()) > 0)
        self.call("admin", "GET", "/api/integrations", check=lambda r: "test_mode" in r.json())
        self.webhook(tag)

    def webhook(self, tag: str) -> None:
        hook = "/api/whatsapp/webhook"
        self.call(None, "GET", hook, params={"hub.mode": "subscribe", "hub.verify_token": "wrong", "hub.challenge": "x"}, expect=(403,))
        if self.verify_token:
            self.call(None, "GET", hook, params={"hub.mode": "subscribe", "hub.verify_token": self.verify_token, "hub.challenge": "42"}, check=lambda r: r.text == "42")
        else:
            self.needs_account.append("GET /api/whatsapp/webhook success needs --verify-token")
        body = json.dumps({"entry": [{"changes": [{"value": {"contacts": [{"wa_id": SAMPLE_LEAD, "profile": {"name": "Sweep Employer"}}],
                                                             "messages": [{"from": SAMPLE_LEAD, "id": f"wamid.sweep.{tag}", "type": "text",
                                                                           "text": {"body": "We are hiring 2 Python developers in Hyderabad, 4 LPA"}}]}}]}]}).encode()
        headers = {"content-type": "application/json"}
        if self.app_secret:
            headers["x-hub-signature-256"] = "sha256=" + hmac.new(self.app_secret.encode(), body, hashlib.sha256).hexdigest()
        self.covered.add(("POST", hook))
        r = self.anon.post(hook, content=body, headers=headers)
        if r.status_code == 403 and not self.app_secret:
            self.needs_account.append("POST /api/whatsapp/webhook refused an unsigned call (correct); pass --app-secret to test the success path")
            self.covered |= {("GET", "/api/leads/unread"), ("GET", "/api/leads")}
        elif r.status_code != 200:
            self.failures.append(f"POST {hook}: {r.status_code} {r.text[:120]}")
        self.call("admin", "GET", "/api/leads/unread", check=lambda r: "unread" in r.json())
        rows = self.call("admin", "GET", "/api/leads").json()
        lead = next((t for t in rows if t["phone"] == SAMPLE_LEAD), None)
        if lead is None:
            self.failures.append("the WhatsApp message from an unknown number should become a lead")
            return
        path = f"/api/leads/{lead['id']}"
        self.call("admin", "GET", "/api/leads/{lead_id}", path, check=lambda r: len(r.json()["messages"]) > 0)
        self.call("admin", "GET", "/api/leads/{lead_id}/suggest", f"{path}/suggest", check=lambda r: r.json()["lead_id"] == lead["id"])
        self.call("admin", "POST", "/api/leads/{lead_id}/reply", f"{path}/reply", json={"text": "Thanks, we will call you."})
        self.call("admin", "POST", "/api/leads/{lead_id}/status", f"{path}/status", json={"status": "dismissed", "note": "Sweep test."},
                  check=lambda r: r.json()["status"] == "dismissed")

    def google_and_close(self, ngo_listing: str) -> None:
        self.call("admin", "GET", "/api/integrations/google/start", expect=(303,), needs_account=True)
        self.call("admin", "GET", "/api/integrations/google/callback", params={"error": "access_denied"}, expect=(303,), needs_account=True)
        if self.google_connected:
            self.covered.add(("POST", "/api/integrations/google/disconnect"))
            self.needs_account.append("POST /api/integrations/google/disconnect was skipped: it would drop the connected Google account")
        else:
            self.call("admin", "POST", "/api/integrations/google/disconnect")
        self.call("admin", "POST", "/api/listings/{oid}/close", f"/api/listings/{ngo_listing}/close", check=lambda r: r.json()["status"] == "closed")

    def sign_out(self) -> None:
        self.covered.add(("POST", "/api/auth/logout"))
        r = self.send("s003", "POST", "/api/auth/logout")
        if r.status_code != 200 or self.clients["s003"].get("/api/auth/me").status_code != 401:
            self.failures.append("signing out should end the session")


def all_routes() -> set[tuple[str, str]]:
    """Every method and path the app serves."""
    from fastapi.routing import APIRoute

    from api.server import app

    def walk(routes):
        for r in routes:
            if isinstance(r, APIRoute):
                yield from ((m, r.path) for m in r.methods)
            elif hasattr(r, "original_router"):
                yield from walk(r.original_router.routes)
    return set(walk(app.routes))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m eval.sweep")
    ap.add_argument("--base", default="http://localhost:8000")
    ap.add_argument("--password", help="the demo password, when the server is not in demo mode")
    ap.add_argument("--verify-token", help="WHATSAPP_VERIFY_TOKEN, to test Meta's webhook check")
    ap.add_argument("--app-secret", help="WHATSAPP_APP_SECRET, to sign the test webhook call")
    ap.add_argument("--yes-this-is-a-test-server", action="store_true")
    a = ap.parse_args(argv)
    if not re.match(r"https?://(localhost|127\.0\.0\.1)(:|/|$)", a.base) and not a.yes_this_is_a_test_server:
        print("This leaves test data behind. For a server that is not on this machine, add --yes-this-is-a-test-server.", file=sys.stderr)
        return 2
    s = Sweep(a.base, a.password, a.verify_token, a.app_secret)
    s.run()
    routes = all_routes()
    missing = sorted(routes - s.covered, key=lambda x: x[1])
    unknown = sorted(s.covered - routes, key=lambda x: x[1])
    print(f"{len(s.covered & routes)} of {len(routes)} routes called. {s.calls} calls as the right person, {s.denied} refused as the wrong one.")
    for line in s.needs_account:
        print("needs a real account:", line)
    for m, p in missing:
        print("NOT CALLED:", m, p)
    for m, p in unknown:
        print("NOT A ROUTE:", m, p)
    for f in s.failures:
        print("FAIL:", f)
    print("all passed" if not (s.failures or missing or unknown) else f"{len(s.failures)} failed, {len(missing)} not called")
    return 1 if s.failures or missing or unknown else 0


if __name__ == "__main__":
    raise SystemExit(main())
