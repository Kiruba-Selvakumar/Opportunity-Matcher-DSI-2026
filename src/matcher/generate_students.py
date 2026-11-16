"""Synthetic raw students. See IMPLEMENTATION_PLAN.md sections 4.2 and 5.1."""
from __future__ import annotations

import csv
import hashlib
import random
from pathlib import Path

import numpy as np
import pandas as pd

from .config import MESSY_SHARE, MISSING_SHARE, N_STUDENTS, PATHS, SEED

COLUMNS = ["student_id", "name", "phone", "email", "branch", "college_name", "college_town", "grad_year",
           "cgpa_text", "backlogs", "skills_text", "english_text", "languages_text", "can_relocate_text",
           "budget_text", "family_limits_text", "program"]

# The NGO runs two programs: Placements (ready for jobs) and Get Skills (training first). Fixed for the three demo students.
PROGRAM_OF_HEROES = {"S001": "Placements", "S002": "Get Skills", "S003": "Get Skills"}
GET_SKILLS_SHARE = 0.35


def program_for(student_id: str) -> str:
    """Which program a synthetic student came through. A hash of the ID, so the seeded random draws stay unchanged."""
    if student_id in PROGRAM_OF_HEROES:
        return PROGRAM_OF_HEROES[student_id]
    bucket = int(hashlib.sha256(student_id.encode()).hexdigest()[:8], 16) / 0xFFFFFFFF
    return "Get Skills" if bucket < GET_SKILLS_SHARE else "Placements"

BRANCHES = [("CSE", 0.45), ("CSE (AI and ML)", 0.15), ("CSE (Data Science)", 0.10), ("IT", 0.12),
            ("ECE", 0.12), ("EEE", 0.06)]

TOWNS = ["Warangal", "Khammam", "Karimnagar", "Nizamabad", "Nalgonda", "Mahabubnagar", "Guntur",
         "Vijayawada", "Tirupati", "Visakhapatnam"]

COLLEGES = [
    ("Sri Venkata Institute of Technology", "Khammam"),
    ("Godavari College of Engineering", "Nizamabad"),
    ("Kakatiya Institute of Engineering Sciences", "Warangal"),
    ("Krishna Valley Engineering College", "Vijayawada"),
    ("Nallamala Institute of Technology", "Guntur"),
    ("Deccan Plateau College of Engineering", "Mahabubnagar"),
    ("Manair Institute of Engineering", "Karimnagar"),
    ("Sagar Hills College of Technology", "Nalgonda"),
    ("Seshachalam Engineering College", "Tirupati"),
    ("Bay Coast Institute of Technology", "Visakhapatnam"),
    ("Orugallu Technical Institute", "Warangal"),
    ("Munneru College of Engineering", "Khammam"),
    ("Amaravathi Institute of Engineering", "Guntur"),
    ("Simhachalam College of Technology", "Visakhapatnam"),
    ("Telangana Rural Engineering College", "Karimnagar"),
]

FIRST_NAMES = ["Sravani", "Lakshmi", "Ravi", "Divya", "Anil", "Harika", "Venkat", "Priya", "Suresh", "Mounika",
               "Kiran", "Swathi", "Naveen", "Anusha", "Srinivas", "Pooja", "Mahesh", "Keerthi", "Rajesh", "Bhavana",
               "Sandeep", "Deepika", "Vamsi", "Sowmya", "Pavan", "Madhavi", "Arjun", "Neelima", "Charan", "Haritha",
               "Tarun", "Sirisha", "Manoj", "Aparna", "Ashok", "Ramya", "Teja", "Vijaya", "Karthik", "Jyothi"]
SURNAMES = ["Reddy", "Naidu", "Rao", "Sharma", "Goud", "Varma", "Chowdary", "Yadav", "Kumar", "Raju", "Prasad",
            "Murthy", "Babu", "Patel", "Singh", "Devi", "Gupta", "Setty", "Nayak", "Raman", "Chandra", "Mohan",
            "Swamy", "Shetty", "Pillai"]

SKILL_POOLS = {
    "CSE": ["Python", "Java", "C", "C++", "SQL", "Data Structures", "Algorithms", "OOP", "DBMS", "HTML", "CSS",
            "JavaScript", "React", "Node.js", "Git", "Linux", "Django", "Flask", "Spring Boot", "MySQL",
            "Manual Testing", "Excel"],
    "CSE (AI and ML)": ["Python", "Machine Learning", "Pandas", "NumPy", "Scikit-learn", "Deep Learning", "SQL",
                        "Statistics", "Git", "Data Structures", "NLP", "Computer Vision", "Generative AI Basics"],
    "CSE (Data Science)": ["Python", "SQL", "Excel", "Pandas", "Power BI", "Tableau", "Statistics",
                           "Data Visualization", "Data Cleaning", "Machine Learning", "MySQL"],
    "ECE": ["C", "Embedded C", "Arduino", "IoT", "MATLAB", "VLSI Basics", "Python", "Networking Basics",
            "PCB Design", "Linux"],
    "EEE": ["C", "MATLAB", "PLC", "AutoCAD Electrical", "Python", "Excel", "Embedded C", "IoT", "Hardware Basics"],
}
SKILL_POOLS["IT"] = SKILL_POOLS["CSE"]

SOFT_SKILLS = ["English Communication", "Written Communication", "Teamwork", "Problem Solving", "Time Management",
               "Presentation", "Adaptability", "Critical Thinking", "Attention to Detail", "Documentation"]
LOCAL_SKILLS = ["NPTEL Programming in Java", "NPTEL Python for Data Science", "NPTEL Data Structures",
                "AMCAT Certified", "TCS NQT Qualified", "Infosys Springboard Certificate", "Coursera Certificate",
                "HackerRank Certificate", "CodeChef Rated", "LeetCode Practice", "Mini Project", "Major Project",
                "Quantitative Aptitude", "Logical Reasoning"]

ABBR = {"Python": "py", "Machine Learning": "ml", "JavaScript": "js", "React": "reactjs", "C++": "cpp",
        "OOP": "oops", "DBMS": "dbms", "Data Structures": "ds"}

FAMILY_TEXT = {"none": "none", "near_home_only": "parents want me near home", "no_night_shift": "no night shifts",
               "safe_workplace_required": "need a safe workplace"}

HEROES = {
    "S001": dict(name="Lakshmi Prasanna", branch="CSE", town="Khammam", grad_year=2026, cgpa_text="7.8",
                 backlogs="0", skills_text="Python, SQL, Git, Excel, English Communication", english_text="good",
                 languages_text="Telugu, English", can_relocate_text="no", budget_text="3000",
                 family_limits_text="parents want me near home"),
    "S002": dict(name="Ravi Teja", branch="CSE (AI and ML)", town="Guntur", grad_year=2026, cgpa_text="78%",
                 backlogs="0",
                 skills_text="know basic python, did mini project in ml, little bit sql. english ok",
                 english_text="ok", languages_text="Telugu, English, Hindi", can_relocate_text="yes",
                 budget_text="15000", family_limits_text="none"),
    "S003": dict(name="Divya Sree", branch="ECE", town="Warangal", grad_year=2027, cgpa_text="7.2",
                 backlogs="1", skills_text="Embedded C, Arduino, IoT, C, MATLAB", english_text="can manage",
                 languages_text="Telugu, English", can_relocate_text="maybe, need to ask parents",
                 budget_text="0", family_limits_text="no night shifts"),
}


def _wchoice(rnd: random.Random, items, weights):
    return rnd.choices(items, weights=weights, k=1)[0]


def _pick_skills(rnd: random.Random, branch: str) -> list[str]:
    pool = SKILL_POOLS[branch]
    k = rnd.randint(3, 7)
    weights = [len(pool) - i for i in range(len(pool))]
    chosen: list[str] = []
    while len(chosen) < min(k, len(pool)):
        s = _wchoice(rnd, pool, weights)
        if s not in chosen:
            chosen.append(s)
    return chosen


def _maybe_abbr(rnd: random.Random, s: str, p: float = 0.5) -> str:
    return ABBR[s] if s in ABBR and rnd.random() < p else s.lower()


def _messy_skills(rnd: random.Random, tech: list[str]) -> str:
    t = (tech * 2)[:4]
    s1, s2, s3, s4 = (_maybe_abbr(rnd, x) for x in t)
    tpl = rnd.randrange(5)
    if tpl == 0:
        return f"know basic {s1}, did mini project in {s2}"
    if tpl == 1:
        return f"{s1} and {s2} (intermediate), learning {s3}"
    if tpl == 2:
        return f"{s1}/{s2}/{s3} , nptel certified in {s4}"
    if tpl == 3:
        return f"done 2 projects using {s1} + {s2}. english ok"
    a1, a2 = (ABBR.get(x, x.lower()) for x in t[:2])
    return f"{a1}, {a2}, little bit {s3}"


def is_messy_skills_text(text: str, vocab: set[str]) -> bool:
    return any(p.strip() not in vocab for p in text.split(","))


def generate_students(n: int = N_STUDENTS, seed: int = SEED) -> pd.DataFrame:
    rnd = random.Random(seed)
    rng = np.random.default_rng(seed)
    ids = [f"S{i:03d}" for i in range(1, n + 1)]
    heroes = [i for i in ids if i in HEROES]
    others = [i for i in ids if i not in HEROES]
    n_messy = round(MESSY_SHARE * n)
    messy_ids = set(rnd.sample(others, max(0, n_messy - 1))) | ({"S002"} if "S002" in ids else set())
    n_missing = round(MISSING_SHARE * n)
    missing_ids = dict.fromkeys(rnd.sample(others, n_missing))
    blank_fields = ["cgpa_text", "english_text", "budget_text", "can_relocate_text"]
    for sid in missing_ids:
        missing_ids[sid] = rnd.choice(blank_fields)

    # make sure every branch appears at least once among the generated students
    branch_names = [b for b, _ in BRANCHES]
    branch_w = [w for _, w in BRANCHES]
    forced = {}
    needed = [b for b in branch_names if b not in {HEROES[h]["branch"] for h in heroes}]
    for b, sid in zip(needed, rnd.sample(others, len(needed))):
        forced[sid] = b

    rows = []
    for i, sid in enumerate(ids):
        name = None
        first = rnd.choice(FIRST_NAMES)
        last = rnd.choice(SURNAMES)
        phone = str(rnd.choice("6789")) + "".join(rnd.choice("0123456789") for _ in range(9))
        if sid in HEROES:
            h = HEROES[sid]
            name = h["name"]
            first, last = name.split(" ", 1)
        else:
            name = f"{first} {last}"
        email = f"{first.lower()}.{last[0].lower()}{i + 1}@example.com"

        if sid in HEROES:
            h = HEROES[sid]
            colleges = [c for c in COLLEGES if c[1] == h["town"]]
            college = colleges[0][0] if colleges else rnd.choice(COLLEGES)[0]
            rows.append(dict(student_id=sid, name=name, phone=phone, email=email, branch=h["branch"],
                             college_name=college, college_town=h["town"], grad_year=h["grad_year"],
                             cgpa_text=h["cgpa_text"], backlogs=h["backlogs"], skills_text=h["skills_text"],
                             english_text=h["english_text"], languages_text=h["languages_text"],
                             can_relocate_text=h["can_relocate_text"], budget_text=h["budget_text"],
                             family_limits_text=h["family_limits_text"], program=program_for(sid)))
            continue

        messy = sid in messy_ids
        branch = forced.get(sid) or _wchoice(rnd, branch_names, branch_w)
        college, town = rnd.choice(COLLEGES)
        grad_year = _wchoice(rnd, [2025, 2026, 2027], [0.2, 0.5, 0.3])
        cgpa = round(float(np.clip(rng.normal(7.0, 0.9), 5.0, 9.6)), 1)
        backlogs = _wchoice(rnd, [0, 1, 2, 3], [0.7, 0.15, 0.1, 0.05])
        level = _wchoice(rnd, ["basic", "intermediate", "fluent"], [0.35, 0.45, 0.20])
        langs = ["Telugu"] + (["English"] if rnd.random() < 0.85 else []) + (["Hindi"] if rnd.random() < 0.40 else [])
        relocate = _wchoice(rnd, ["yes", "no", "maybe"], [0.45, 0.40, 0.15])
        bucket = _wchoice(rnd, [0, 1, 2, 3], [0.25, 0.35, 0.25, 0.15])
        if bucket == 0:
            budget = 0
        elif bucket == 1:
            budget = rnd.randrange(1000, 5001, 500)
        elif bucket == 2:
            budget = rnd.randrange(5500, 15001, 500)
        else:
            budget = rnd.randrange(16000, 30001, 1000)
        fam = _wchoice(rnd, ["none", "near_home_only", "no_night_shift", "safe_workplace_required"],
                       [0.55, 0.20, 0.15, 0.10])
        fams = [] if fam == "none" else [fam]
        if rnd.random() < 0.10:
            extra = rnd.choice([f for f in ["near_home_only", "no_night_shift", "safe_workplace_required"]
                                if f not in fams])
            fams.append(extra)

        tech = _pick_skills(rnd, branch)
        if messy:
            skills_text = _messy_skills(rnd, tech)
        else:
            skills = list(tech)
            skills += rnd.sample(SOFT_SKILLS, rnd.randint(1, 2))
            if rnd.random() < 0.5:
                skills.append(rnd.choice(LOCAL_SKILLS))
            skills_text = ", ".join(skills)

        eng_words = {"basic": ["basic", "little"], "intermediate": ["ok", "good", "can manage"],
                     "fluent": ["fluent", "very good"]}
        english_text = rnd.choice(eng_words[level])

        if messy:
            cgpa_text = rnd.choice([f"{round(cgpa * 9.5)}%", f"{cgpa}/10", f"{cgpa:g} cgpa"])
            if budget == 0:
                budget_text = "nil"
            elif budget >= 2000 and rnd.random() < 0.4:
                budget_text = f"can manage {budget // 1000}-{budget // 1000 + 1}k"
            elif budget % 1000 == 0:
                budget_text = f"{budget // 1000}k"
            else:
                budget_text = str(budget)
            reloc_text = {"yes": rnd.choice(["yes", "y", "ok"]), "no": rnd.choice(["no", "n"]),
                          "maybe": "maybe, need to ask parents"}[relocate]
            parts = ["telugu"] + (["english"] if "English" in langs else [])
            if "Hindi" in langs:
                parts.append(rnd.choice(["hindi", "little hindi"]))
            languages_text = " and ".join(parts)
        else:
            cgpa_text = str(cgpa)
            budget_text = str(budget)
            reloc_text = {"yes": "yes", "no": "no", "maybe": "maybe, need to ask parents"}[relocate]
            languages_text = ", ".join(langs)

        row = dict(student_id=sid, name=name, phone=phone, email=email, branch=branch, college_name=college,
                   college_town=town, grad_year=grad_year, cgpa_text=cgpa_text, backlogs=str(backlogs),
                   skills_text=skills_text, english_text=english_text, languages_text=languages_text,
                   can_relocate_text=reloc_text, budget_text=budget_text,
                   family_limits_text=", ".join(FAMILY_TEXT[f] for f in fams) if fams else "none")
        if sid in missing_ids:
            row[missing_ids[sid]] = ""
        row["program"] = program_for(sid)
        rows.append(row)
    return pd.DataFrame(rows, columns=COLUMNS)


def holds_real_data(path: Path | str | None = None) -> bool:
    """True when the raw students file is not the generated sample, whose every email is at example.com.
    Generating over it would overwrite real people, and then the contact book made from them."""
    p = Path(path or PATHS["students_raw"])
    if not p.exists():
        return False
    with p.open(newline="") as f:
        emails = [(r.get("email") or "").strip().lower() for r in csv.DictReader(f)]
    return not (emails and all(e.endswith("@example.com") for e in emails))


def main() -> None:
    if holds_real_data():
        print(f"kept {PATHS['students_raw']}: it is not the sample data. Delete it first to make sample data again.")
        return
    df = generate_students()
    PATHS["students_raw"].parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(PATHS["students_raw"], index=False, lineterminator="\n")
    print(f"wrote {len(df)} students to {PATHS['students_raw']}")


if __name__ == "__main__":
    main()
