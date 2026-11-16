"""Synthetic raw opportunities. See IMPLEMENTATION_PLAN.md sections 4.4, 5.2 and 5.3."""
from __future__ import annotations

import hashlib
import random
from datetime import date, timedelta

import pandas as pd

from .config import PATHS, SEED

COLUMNS = ["opp_id", "type", "title", "org_name", "job_family", "required_skills_text", "city", "mode",
           "pay_text", "upfront_cost_text", "hours_per_week", "night_shift", "safety_score",
           "languages_required_text", "description", "starts_on", "duration_weeks", "batch_every_weeks", "apply_by"]

ORGS = ["Nimbus Softworks", "Kaveri Systems", "BlueLotus Technologies", "Orchid Digital", "Tungabhadra Labs",
        "Pinnacle Infoserve", "Sunrise Data Works", "Marigold Cloud", "Gopuram Software", "Indus Circuit Works",
        "Lakeview Analytics", "Banyan Tech Services", "Cedar Support Desk", "Vajra Security Labs", "Saffron Apps",
        "Mango Grove Systems", "Kolleru Networks", "Charminar Digital", "Hilltop QA Services", "Neem Robotics"]

# family -> (titles, skill choices (a tuple means "pick one of these"), pay range in LPA)
FAMILIES = [
    ("Software Trainee", ["Software Trainee", "Graduate Engineer Trainee"],
     ["Data Structures", "OOP", ("Java", "Python"), "SQL"], (3.0, 4.5)),
    ("Python Developer", ["Junior Python Developer"], ["Python", ("Django", "Flask"), "SQL", "Git"], (3.0, 5.0)),
    ("Java Developer", ["Java Developer (Fresher)"], ["Java", "Spring Boot", "SQL", "OOP"], (3.0, 5.0)),
    ("Frontend Developer", ["Frontend Developer Intern"], ["HTML", "CSS", "JavaScript", "React"], (2.5, 4.5)),
    ("Full Stack Developer", ["Full Stack Trainee"], ["JavaScript", "React", "Node.js", "MongoDB"], (3.0, 6.0)),
    ("QA / Manual Testing", ["QA Tester", "Manual Test Engineer"],
     ["Manual Testing", "Test Case Writing", "Bug Reporting", "SQL"], (2.5, 4.0)),
    ("Automation Testing", ["Automation Test Engineer"], ["Selenium", ("Java", "Python"), "API Testing"], (3.0, 5.0)),
    ("Technical Support", ["Technical Support Engineer"],
     ["Technical Support", "Troubleshooting", "English Communication", "Networking Basics"], (2.5, 3.6)),
    ("IT Helpdesk", ["IT Helpdesk Associate"], ["Windows Administration", "Hardware Basics", "Customer Handling"],
     (2.4, 3.2)),
    ("Data Analyst", ["Data Analyst Trainee", "Junior Data Analyst"],
     ["Excel", "SQL", ("Power BI", "Tableau"), "Python"], (3.0, 5.0)),
    ("ML / Data Science Intern", ["ML Intern"], ["Python", "Machine Learning", "Pandas", "Scikit-learn"],
     (2.4, 4.8)),
    ("Cloud Support", ["Cloud Support Associate"], ["AWS Basics", "Linux", "Networking Basics"], (3.5, 5.5)),
    ("SOC Analyst", ["SOC Analyst Trainee"], ["Cyber Security Basics", "Network Security", "Linux"], (3.0, 4.5)),
    ("Embedded Systems", ["Embedded Systems Trainee"], ["Embedded C", "C", "Arduino", "IoT"], (2.5, 4.0)),
    ("Android Developer", ["Android Developer Intern"], ["Android Development", ("Kotlin", "Java"), "Git"],
     (2.5, 4.5)),
]
NIGHT_FAMILIES = {"Technical Support", "IT Helpdesk", "SOC Analyst"}
LOCAL_TOWNS = {"Warangal", "Visakhapatnam", "Vijayawada"}

JOB_CITIES = [("Hyderabad", 10), ("Bengaluru", 5), ("Chennai", 3), ("Pune", 2), ("Warangal", 2),
              ("Visakhapatnam", 2), ("Vijayawada", 1)]
# job family index list: each family twice gives 30 jobs
REMOTE_FAMILY_IDX = [9, 9, 5, 10, 11]  # Data Analyst x2, QA, ML Intern, Cloud Support

TRAINING_TYPES = [
    # title, mode, city, cost, hours, skills, languages
    ("NPTEL Style Online Course", "remote", "Remote", 0, 6, "Python, Data Structures, Mini Project", "English"),
    ("Online Full Stack Course", "remote", "Remote", 1500, 10, "JavaScript, React, Node.js, HTML, CSS", "English"),
    ("Weekend Python Bootcamp", "onsite", "Hyderabad", 8000, 12, "Python, SQL, Git", "English"),
    ("Cloud Practitioner Prep", "remote", "Remote", 2500, 8, "AWS Basics, Linux", "English"),
    ("Data Analytics with Excel and Power BI", "onsite", "Vijayawada", 4000, 10,
     "Excel, Power BI, SQL, Data Visualization", "English, Telugu"),
    ("Software Testing Course", "onsite", "Hyderabad", 12000, 20,
     "Manual Testing, Selenium, Test Case Writing, Bug Reporting", "English"),
    ("Embedded Systems Lab Course", "onsite", "Warangal", 6000, 15, "Embedded C, Arduino, IoT",
     "English, Telugu"),
    ("Spoken English for Interviews", "remote", "Remote", 1500, 4, "English Communication, Interview Readiness",
     "English"),
    ("Aptitude and Interview Prep", "remote", "Remote", 0, 5,
     "Quantitative Aptitude, Logical Reasoning, Interview Readiness", "English"),
    ("Full Time 3 Month Coding Bootcamp", "onsite", "Bengaluru", 30000, 45,
     "Data Structures, Algorithms, Java, SQL", "English"),
]
# Training schedules: weeks one batch runs, and a new batch every N weeks. Fixed dates, so two runs give the same files.
TRAINING_SCHEDULE = {
    "NPTEL Style Online Course": (8, 4), "Online Full Stack Course": (12, 4), "Weekend Python Bootcamp": (6, 6),
    "Cloud Practitioner Prep": (4, 4), "Data Analytics with Excel and Power BI": (6, 3), "Software Testing Course": (8, 4),
    "Embedded Systems Lab Course": (10, 8), "Spoken English for Interviews": (4, 2), "Aptitude and Interview Prep": (3, 2),
    "Full Time 3 Month Coding Bootcamp": (12, 12),
}
FIRST_BATCH = "2026-11-02"   # a Monday; batch t starts t % 5 weeks after it


def _batch_start(t: int) -> str:
    from datetime import date, timedelta
    return (date.fromisoformat(FIRST_BATCH) + timedelta(weeks=t % 5)).isoformat()


TRAINING_PROVIDERS = ["SkillBridge Academy", "Kaveri Learning", "Lotus Institute", "CodeNest Training",
                      "Deccan Upskill", "Orchid Academy", "Tech Sarathi", "Bright Path Learning"]

MENTORS = [
    ("Alumni Mentor: Backend (Python and Java)", "Python, Django, SQL"),
    ("Alumni Mentor: Data Analytics", "Excel, SQL, Power BI, Python"),
    ("Alumni Mentor: QA and Testing", "Manual Testing, Selenium, Test Case Writing"),
    ("Alumni Mentor: Embedded Systems", "Embedded C, Arduino, IoT"),
    ("Alumni Mentor: Cloud and Support", "AWS Basics, Linux, Technical Support"),
]
# How long each mentor programme runs, at about 2 hours a week. Fixed values, so the rest of the data stays the same.
MENTOR_WEEKS = {"Alumni Mentor: Backend (Python and Java)": 6, "Alumni Mentor: Data Analytics": 4,
                "Alumni Mentor: QA and Testing": 5, "Alumni Mentor: Embedded Systems": 8, "Alumni Mentor: Cloud and Support": 4}

# What the role involves, as an employer would write it. Fixed text, so it uses no random draws and the
# rest of the generated data stays the same. Nothing reads it for scoring; students see it on a listing.
FAMILY_ABOUT = {
    "Software Trainee": "Join a trainee batch that learns our codebase, then fixes bugs and builds small features with a senior engineer reviewing your work.",
    "Python Developer": "Build and maintain web back ends: write API endpoints, database queries and tests, and take part in code reviews.",
    "Java Developer": "Work on Java services for our clients: add features, fix defects and write unit tests, with a team lead guiding you.",
    "Frontend Developer": "Turn designs into web pages and components, fix layout bugs across browsers and phones, and work with the back end team.",
    "Full Stack Developer": "Work across the front end and the server on our client projects, from screens to APIs and the database behind them.",
    "QA / Manual Testing": "Test new releases by hand: write test cases, run them, and report bugs clearly so developers can fix them.",
    "Automation Testing": "Write and run automated tests for web apps and APIs, keep them working as the product changes, and report what fails.",
    "Technical Support": "Help customers by phone, chat and email: find out what went wrong, walk them through fixes, and pass harder cases on.",
    "IT Helpdesk": "Look after staff laptops, accounts and printers: set up new machines, fix everyday problems and keep a record of each request.",
    "Data Analyst": "Clean and combine business data, build regular reports and dashboards, and explain what the numbers mean to the team.",
    "ML / Data Science Intern": "Prepare data, train and test simple models, and share results with the data science team for a live project.",
    "Cloud Support": "Watch over client cloud servers, respond to alerts, and help customers with setup and access problems.",
    "SOC Analyst": "Watch security alerts in our operations centre, look into the suspicious ones, and raise real incidents to senior analysts.",
    "Embedded Systems": "Write and test firmware for small devices and sensors, and help debug hardware on the lab bench.",
    "Android Developer": "Build screens and features for our Android apps, fix crashes reported by users, and help with releases.",
}
TRAINING_ABOUT = {
    "NPTEL Style Online Course": "A self-paced online course with weekly lectures and assignments, ending in a mini project you can show employers.",
    "Online Full Stack Course": "Live online classes that take you from web basics to a working full stack app, with a project at the end.",
    "Weekend Python Bootcamp": "Classroom sessions on Saturdays and Sundays covering Python, databases and version control, with practice every week.",
    "Cloud Practitioner Prep": "Online classes and practice tests that prepare you for an entry-level cloud certificate.",
    "Data Analytics with Excel and Power BI": "Hands-on classes in cleaning data and building reports and dashboards, taught in English and Telugu.",
    "Software Testing Course": "A classroom course in manual and automated testing, with real practice projects and help preparing a test portfolio.",
    "Embedded Systems Lab Course": "Lab sessions on microcontrollers, sensors and simple IoT projects, taught in English and Telugu.",
    "Spoken English for Interviews": "Small online groups that practise speaking English and answering common interview questions.",
    "Aptitude and Interview Prep": "Online practice for the aptitude tests and interview rounds that most campus drives use.",
    "Full Time 3 Month Coding Bootcamp": "A full-time, three-month classroom programme in programming and problem solving, with placement help at the end.",
}
MENTOR_ABOUT = ("A working professional from the alumni network meets you online for about two hours a week, "
                "reviews your projects and helps you plan your job search.")


def _skills_text(rnd: random.Random, picks: list[str], messy: bool) -> str:
    if not messy or len(picks) < 3:
        return ", ".join(picks)
    first = [s.lower() for s in picks[:2]]
    rest = [f"{s.lower()} is a plus" for s in picks[2:]]
    return " + ".join(first) + ", " + ", ".join(rest)


def _indian_commas(n: int) -> str:
    s = str(n)
    if len(s) <= 3:
        return s
    head, tail = s[:-3], s[-3:]
    parts = []
    while len(head) > 2:
        parts.insert(0, head[-2:])
        head = head[:-2]
    if head:
        parts.insert(0, head)
    return ",".join(parts + [tail])


def _pay_text(rnd: random.Random, lo: float, hi: float, messy: bool) -> str:
    a = round(rnd.uniform(lo, (lo + hi) / 2), 1)
    b = round(rnd.uniform((lo + hi) / 2, hi), 1)
    if not messy:
        return f"{round((a + b) / 2, 1)} LPA"
    fmt = rnd.randrange(6)
    mid = round((a + b) / 2, 1)
    monthly = int(round(mid * 100000 / 12 / 1000) * 1000)
    if fmt == 0:
        return f"{int(a)}-{int(b) + 1} LPA" if int(a) == int(b) else f"{int(a)}-{int(b)} LPA"
    if fmt == 1:
        return f"{monthly // 1000}k/month"
    if fmt == 2:
        return f"₹ {_indian_commas(monthly)} per month"
    if fmt == 3:
        return f"stipend {monthly // 1000}k"
    if fmt == 4:
        return f"{_indian_commas(int(round(mid * 100000, -3)))} per annum"
    return "not disclosed"


def _apply_by(oid: str) -> str:
    """A last day to apply, counted from today so a fresh build always has open jobs. It comes from a hash of the ID, so every
    other generated value stays the same. Some jobs have none, and the demo employer's two listings stay open."""
    h = int(hashlib.sha256(oid.encode()).hexdigest(), 16)
    if h % 4 == 0 or oid in ("J027", "J028"):
        return ""
    return (date.today() + timedelta(days=5 if h % 5 == 0 else 21 + h % 40)).isoformat()


def generate_opportunities(seed: int = SEED) -> pd.DataFrame:
    rnd = random.Random(seed)
    rows: list[dict] = []

    # ---- jobs ----
    fam_idx = [i for i in range(len(FAMILIES)) for _ in range(2)]
    remote_pool = list(fam_idx)
    remote_picks = []
    for f in REMOTE_FAMILY_IDX:
        remote_pool.remove(f)
        remote_picks.append(f)
    rnd.shuffle(remote_pool)
    cities: list[str] = []
    for city, n in JOB_CITIES:
        cities += [city] * n
    # support and SOC roles that are likely to need local-language skills go to local towns first
    jobs_spec = [(f, "Remote") for f in remote_picks] + list(zip(remote_pool, cities))
    night_ids = [k for k, (f, _) in enumerate(jobs_spec) if FAMILIES[f][0] in NIGHT_FAMILIES]
    night_pick = set(rnd.sample(night_ids, 5))
    deposit_pick = set(rnd.sample(range(len(jobs_spec)), 2))
    messy_pay = set(rnd.sample(range(len(jobs_spec)), 9))
    messy_skills = set(rnd.sample(range(len(jobs_spec)), 9))
    # sort so remote jobs come last in IDs is not required; keep order stable by city then family
    order = sorted(range(len(jobs_spec)), key=lambda k: (jobs_spec[k][1] == "Remote", jobs_spec[k][1], jobs_spec[k][0]))
    job_n = 0
    for k in order:
        f, city = jobs_spec[k]
        fam, titles, pool, (plo, phi) = FAMILIES[f]
        job_n += 1
        n_skills = rnd.randint(2, min(4, len(pool)))
        chosen = list(pool)
        if len(chosen) > n_skills:
            keep = sorted(rnd.sample(range(len(chosen)), n_skills))
            chosen = [chosen[i] for i in keep]
        picks = [rnd.choice(c) if isinstance(c, tuple) else c for c in chosen]
        if fam == "Data Analyst" and "SQL" not in picks:
            picks[-1] = "SQL"
        mode = "remote" if city == "Remote" else rnd.choice(["onsite", "onsite", "hybrid"])
        if fam == "Python Developer" and city == "Remote" and "Python" not in picks:
            picks[0] = "Python"
        langs = ["English"]
        if fam in NIGHT_FAMILIES and city in LOCAL_TOWNS:
            langs.append("Telugu")
        cost_text = "0"
        if k in deposit_pick:
            cost_text = rnd.choice(["Rs 5,000", "Rs 8,000", "Rs 10,000", "5k", "10k"])
        elif rnd.random() < 0.3:
            cost_text = "free"
        pay = (_pay_text(rnd, plo, phi, False) if k not in messy_pay else _pay_text(rnd, plo, phi, True))
        if fam == "ML / Data Science Intern" and k in messy_pay:
            pay = f"stipend {rnd.choice([10, 15, 20])}k"
        rows.append(dict(
            opp_id=f"J{job_n:03d}", type="job", title=rnd.choice(titles), org_name=rnd.choice(ORGS),
            job_family=fam, required_skills_text=_skills_text(rnd, picks, k in messy_skills), city=city,
            mode=mode, pay_text=pay, upfront_cost_text=cost_text, hours_per_week=rnd.randint(40, 54),
            night_shift="yes" if k in night_pick else "no",
            safety_score=rnd.choices([5, 4, 3, 2, 1], weights=[0.3, 0.35, 0.2, 0.1, 0.05])[0],
            languages_required_text=", ".join(langs), description=FAMILY_ABOUT[fam]))
    # one more guaranteed unambiguous QA intern title for the demo
    for r in rows:
        if r["job_family"] == "QA / Manual Testing" and r["city"] == "Remote":
            r["title"] = "QA Intern"
            break

    # ---- training ----
    for t in range(15):
        title, mode, city, cost, hours, skills, langs = TRAINING_TYPES[t % 10]
        about = TRAINING_ABOUT[title]
        if t >= 10:
            cost = max(0, cost + rnd.choice([-500, 0, 500, 1000])) if cost else 0
            hours = max(2, hours + rnd.choice([-2, 0, 2]))
            title = f"{title} (Batch {t - 9 + 1})"
        rows.append(dict(
            opp_id=f"T{t + 1:03d}", type="training", title=title, org_name=rnd.choice(TRAINING_PROVIDERS),
            job_family="Training", required_skills_text=skills, city=city, mode=mode, pay_text="",
            upfront_cost_text="free" if cost == 0 else (f"{cost // 1000}k" if cost % 1000 == 0 and rnd.random() < 0.3
                                                         else f"Rs {_indian_commas(cost)}"),
            hours_per_week=hours, night_shift="no", safety_score=rnd.choice([4, 5, 5]),
            languages_required_text=langs, description=about, starts_on=_batch_start(t),
            duration_weeks=TRAINING_SCHEDULE[TRAINING_TYPES[t % 10][0]][0],
            batch_every_weeks=TRAINING_SCHEDULE[TRAINING_TYPES[t % 10][0]][1]))

    # ---- mentors ----
    for m, (title, skills) in enumerate(MENTORS):
        rows.append(dict(
            opp_id=f"M{m + 1:03d}", type="mentor", title=title, org_name="Alumni Circle",
            job_family="Mentorship", required_skills_text=skills, city="Remote", mode="remote", pay_text="",
            upfront_cost_text="0", hours_per_week=2, night_shift="no", safety_score=5,
            languages_required_text="English", description=MENTOR_ABOUT, duration_weeks=MENTOR_WEEKS[title]))
    for r in rows:
        r["apply_by"] = _apply_by(r["opp_id"]) if r["type"] == "job" else ""
    df = pd.DataFrame(rows, columns=COLUMNS)
    for col in ("duration_weeks", "batch_every_weeks"):   # jobs and mentors have no schedule: keep the column whole numbers
        df[col] = df[col].map(lambda v: "" if pd.isna(v) else str(int(v)))
    df["starts_on"] = df["starts_on"].fillna("")
    return df


def main() -> None:
    from .generate_students import holds_real_data
    if holds_real_data():
        print(f"kept {PATHS['opportunities_raw']}: the students file is not the sample data, so this one is left alone too.")
        return
    df = generate_opportunities()
    PATHS["opportunities_raw"].parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(PATHS["opportunities_raw"], index=False, lineterminator="\n")
    print(f"wrote {len(df)} opportunities to {PATHS['opportunities_raw']}")


if __name__ == "__main__":
    main()
