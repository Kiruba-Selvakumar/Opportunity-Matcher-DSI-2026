"""A student's data export as one readable, printable HTML page. Every value is escaped."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from html import escape

IST = timezone(timedelta(hours=5, minutes=30))

STATUS = {"interested": "Interested", "shared": "Shared with employer", "shortlisted": "Shortlisted",
          "interview": "Interview", "offered": "Offer", "hired": "Hired", "declined": "Not shared",
          "not_a_fit": "Not a fit", "withdrawn": "Withdrawn"}
LIMITS = {"near_home_only": "Near home only", "no_night_shift": "No night shifts",
          "safe_workplace_required": "Safe workplace required"}
WHO = {"student": "You", "ngo": "NGO staff", "lister": "Employer"}
FIELD = {"can_relocate": "whether you can move", "budget": "your budget", "family_limits": "family limits",
         "languages": "languages", "english_level": "English level", "extra_skills": "skills"}

CSS = """
:root { --bg:#f3efe6; --surface:#fffcf6; --line:#e2dacb; --ink:#1f1c17; --soft:#544e44; --faint:#6e675b; --accent:#2c6148; }
* { box-sizing: border-box; }
body { margin:0; background:var(--bg); color:var(--ink); font:15px/1.55 system-ui, -apple-system, "Segoe UI", sans-serif; }
main { max-width:760px; margin:0 auto; padding:24px 16px 48px; }
h1 { font:600 26px/1.25 Georgia, serif; margin:0 0 4px; }
h2 { font:600 19px/1.3 Georgia, serif; margin:0 0 10px; color:var(--accent); }
h3 { font-size:15px; margin:0; }
section { background:var(--surface); border:1px solid var(--line); border-radius:10px; padding:16px 18px; margin-top:16px; }
.sub, .muted { color:var(--soft); }
.faint { color:var(--faint); font-size:13px; }
.tip { background:#e3ebdf; border-radius:8px; padding:10px 12px; margin-top:12px; font-size:14px; }
dl { display:grid; grid-template-columns:minmax(120px, 36%) 1fr; gap:6px 14px; margin:0; }
dt { color:var(--soft); }
dd { margin:0; overflow-wrap:anywhere; }
ul { margin:6px 0 0; padding-left:20px; }
.item { border-top:1px solid var(--line); padding:12px 0; }
.item:first-of-type { border-top:0; padding-top:0; }
.status { display:inline-block; border:1px solid var(--line); border-radius:99px; padding:0 8px; font-size:13px; }
.text { white-space:pre-wrap; overflow-wrap:anywhere; margin:4px 0 0; }
@media (max-width:480px) { dl { grid-template-columns:1fr; gap:0 0; } dd { margin-bottom:8px; } }
@media print { body { background:#fff; } .tip { display:none; } section { break-inside:avoid; border-color:#ccc; } }
"""


def when(iso: str | None, with_time: bool = True) -> str:
    """'2026-10-14T09:37:41+00:00' -> '14 Oct 2026, 3:07 pm' (India time)."""
    if not iso:
        return ""
    try:
        t = datetime.fromisoformat(iso)
    except ValueError:
        return iso
    if t.tzinfo is None:
        t = t.replace(tzinfo=timezone.utc)
    t = t.astimezone(IST)
    day = f"{t.day} {t:%b %Y}"
    if not with_time:
        return day
    return f"{day}, {t.hour % 12 or 12}:{t:%M} {'am' if t.hour < 12 else 'pm'}"


def rupees(n: int) -> str:
    """Indian digit grouping, as the web app shows it: 150000 -> 'Rs 1,50,000'."""
    s = str(abs(int(n)))
    head, tail = s[:-3], s[-3:]
    while len(head) > 2:
        tail = head[-2:] + "," + tail
        head = head[:-2]
    return "Rs " + ("-" if n < 0 else "") + (head + "," + tail if head else tail)


def _e(v) -> str:
    return escape(str(v))


def _rows(pairs: list[tuple[str, str]]) -> str:
    return "<dl>" + "".join(f"<dt>{_e(k)}</dt><dd>{_e(v)}</dd>" for k, v in pairs) + "</dl>"


def _listing(oid: str | None, titles: dict[str, tuple[str, str]]) -> str:
    if not oid:
        return ""
    title, org = titles.get(oid, ("A listing that is no longer open", ""))
    return f"{title}, {org}" if org else title


def _about(d: dict) -> str:
    p = d["profile"]
    pairs = [("Name", d.get("name") or "Not on file"), ("Username", d["account"]["username"]),
             ("Student number", p["student_id"]), ("Branch", p["branch"]), ("College town", p["college_town"]),
             ("Graduation year", p["grad_year"]),
             ("CGPA", p["cgpa"] if p.get("cgpa") is not None else "Not on file"),
             ("Backlogs", p["backlogs"] if p.get("backlogs") is not None else "Not on file"),
             ("Projects", p.get("projects", 0))]
    return ("<section><h2>About you</h2>" + _rows(pairs) +
            '<p class="faint">These come from your college records. To correct one, message your placement officer.</p></section>')


def _skills(d: dict) -> str:
    p, extra = d["profile"], set(d.get("extra_skills") or [])
    mine = ' <span class="faint">(added by you)</span>'
    items = "".join(f"<li>{_e(s)}{mine if s in extra else ''}</li>" for s in p.get("skills", []))
    out = "<section><h2>Your skills</h2>" + (f"<ul>{items}</ul>" if items else '<p class="muted">No skills on file yet.</p>')
    if p.get("unmatched"):
        out += f'<p class="faint">Words we could not match to a skill: {_e(", ".join(p["unmatched"]))}.</p>'
    return out + "</section>"


RESUME_FROM = {"student": "you", "ngo": "NGO staff", "bulk": "NGO staff (bulk upload)"}


def _resume(d: dict) -> str:
    """The stored resume as the student may see it: when and by whom it was added, and its score. Never the text."""
    cv = d.get("resume")
    if not cv:
        return '<section><h2>Your resume</h2><p class="muted">We do not hold a resume for you.</p></section>'
    pairs = [("Added", f"{when(cv.get('uploaded_at'), False)} by {RESUME_FROM.get(cv.get('source'), 'NGO staff')}"),
             ("Pages", cv.get("pages", "")), ("Resume score", f"{cv.get('score', '')} ({cv.get('grade') or 'not graded'})")]
    out = "<section><h2>Your resume</h2>" + _rows(pairs)
    if cv.get("skills"):
        out += f'<p class="faint">Skills found in it: {_e(", ".join(cv["skills"]))}.</p>'
    if cv.get("tips"):
        out += "<p><strong>Tips:</strong></p><ul>" + "".join(f"<li>{_e(t)}</li>" for t in cv["tips"]) + "</ul>"
    return out + '<p class="faint">To have your stored resume removed, message your placement officer.</p></section>'


def _situation(d: dict) -> str:
    p = d["profile"]
    move = {True: "Yes", False: "No"}.get(p.get("can_relocate"), "You have not told us yet")
    budget = rupees(p["budget"]) if p.get("budget") is not None else "You have not told us yet"
    limits = ", ".join(LIMITS.get(x, x) for x in p.get("family_limits", [])) or "None"
    pairs = [("Can move for a job", move), ("Can spend up front", budget), ("Family limits", limits),
             ("Languages", ", ".join(p.get("languages", [])) or "You have not told us yet"),
             ("English level", (p.get("english_level") or "You have not told us yet").capitalize())]
    out = "<section><h2>What you told us</h2>" + _rows(pairs)
    edited = [FIELD.get(f, f) for f in d.get("edited_fields") or []]
    if edited:
        out += f'<p class="faint">You last changed {_e(", ".join(edited))} on {_e(when(d.get("edited_at"), False))}.</p>'
    c = d.get("completeness")
    if c:
        todo = [i["label"] for i in c.get("items", []) if not i.get("done")]
        out += f'<p class="faint">Your profile is {_e(c["percent"])}% complete.'
        out += (f" Still to fill in: {_e('; '.join(todo))}.</p>" if todo else "</p>")
    return out + "</section>"


def _applications(d: dict) -> str:
    apps = d.get("applications") or []
    if not apps:
        return '<section><h2>Your applications</h2><p class="muted">You have not shown interest in any listing yet.</p></section>'
    out = "<section><h2>Your applications</h2>"
    for a in apps:
        out += (f'<div class="item"><h3>{_e(a["title"])}</h3><p class="muted">{_e(a["org_name"])}, {_e(a["city"])}</p>'
                f'<p><span class="status">{_e(STATUS.get(a["status"], a["status"]))}</span> {_e(a.get("words", ""))}</p>'
                f'<p class="faint">Started {_e(when(a.get("created_at"), False))}</p>')
        for label, key in (("Your note", "student_note"), ("Note from the NGO", "ngo_note"), ("Note from the employer", "employer_note")):
            if a.get(key):
                out += f'<p><strong>{label}:</strong></p><p class="text">{_e(a[key])}</p>'
        steps = a.get("events") or []
        if steps:
            out += "<p><strong>Steps:</strong></p><ul>"
            shown = {a.get("student_note"), a.get("ngo_note"), a.get("employer_note")}
            for ev in steps:
                note = f" ({_e(ev['note'])})" if ev.get("note") and ev["note"] not in shown else ""
                out += f"<li>{_e(when(ev.get('at')))}: {_e(STATUS.get(ev.get('to'), ev.get('to')))}, by {_e(ev.get('by', ''))}{note}</li>"
            out += "</ul>"
        out += "</div>"
    return out + "</section>"


def _saved(d: dict, titles: dict) -> str:
    saved = d.get("saved") or []
    if not saved:
        return '<section><h2>Saved listings</h2><p class="muted">You have not saved any listings.</p></section>'
    return "<section><h2>Saved listings</h2><ul>" + "".join(f"<li>{_e(_listing(o, titles))}</li>" for o in saved) + "</ul></section>"


def _messages(d: dict, titles: dict) -> str:
    msgs = d.get("messages") or []
    if not msgs:
        return '<section><h2>Messages</h2><p class="muted">No messages yet.</p></section>'
    out = "<section><h2>Messages</h2>"
    for m in msgs:
        about = f" · about {_e(_listing(m['about'], titles))}" if m.get("about") else ""
        out += (f'<div class="item"><p class="faint"><strong>{_e(WHO.get(m.get("from"), m.get("from")))}</strong>, '
                f'{_e(when(m.get("at")))}{about}</p><p class="text">{_e(m.get("text", ""))}</p></div>')
    return out + "</section>"


def render(d: dict, titles: dict[str, tuple[str, str]], now: datetime | None = None) -> str:
    """d is the JSON export. titles maps a listing id to (title, organisation), so no raw ids are shown."""
    made = when((now or datetime.now(timezone.utc)).isoformat())
    first = (d.get("name") or d["account"].get("display_name") or "").split(" ")[0]
    head = f"Your data, {first}" if first else "Your data"
    return ("<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
            "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
            f"<title>{_e(head)}</title><style>{CSS}</style></head><body><main>"
            f"<h1>{_e(head)}</h1><p class=\"sub\">Your profile, applications, saved listings and messages in the "
            f"Opportunity Matcher, as of {_e(made)}.</p>"
            "<p class=\"tip\">To keep this as a PDF, open it in your browser, choose Print, then Save as PDF.</p>"
            + _about(d) + _skills(d) + _resume(d) + _situation(d) + _applications(d) + _saved(d, titles) + _messages(d, titles) +
            "<p class=\"faint\">If something here is wrong or you have a question about your data, message your "
            "placement officer.</p></main></body></html>")
