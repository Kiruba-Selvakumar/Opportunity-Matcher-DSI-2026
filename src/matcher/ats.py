"""ATS-style resume scoring: how well a resume reads to a hiring screen, overall and for one listing.

The overall score (0 to 100) checks what screening software and recruiters look for: clear sections, a way to make
contact, named skills, a sensible length, results with numbers, and links to work. The listing score adds how many of the
listing's skills the resume actually names. Each missing piece becomes a plain tip. The report never holds the
resume's text, name, phone or email: only what was found.
"""
from __future__ import annotations

import re

from .parse_text import extract_resume
from .privacy import EMAIL_RE, PHONE_RE

SECTIONS = {  # section -> (heading words, points)
    "education": (r"education|academic(?:s| details| background)?|qualifications?", 8),
    "skills": (r"(?:technical |key |core )?skills|technologies|tools|tech stack", 10),
    "projects": (r"(?:academic |personal |major |mini )?projects?", 10),
    "experience": (r"(?:work )?experience|internships?|employment|work history", 6),
    "certifications": (r"certifications?|certificates?|courses|trainings?", 3),
    "summary": (r"summary|objective|profile|about me|career objective", 3),
}
SECTION_WORD = {"education": "Education", "skills": "Skills", "projects": "Projects", "experience": "Experience or internships",
                "certifications": "Certifications", "summary": "a short summary"}
ACTION = re.compile(r"\b(built|developed|designed|implemented|created|led|improved|reduced|increased|automated|analy[sz]ed|"
                    r"deployed|managed|tested|trained|optimi[sz]ed|organi[sz]ed|wrote|launched|delivered)\b", re.I)
RESULT = re.compile(r"\d+(?:\.\d+)?\s*(?:%|percent|x\b|users|students|customers|records|rows|accuracy|hours|days|lakh|k\b)", re.I)


def _headings(text: str) -> set[str]:
    found = set()
    for line in text.splitlines():
        words = line.strip().strip(":-•*#|").strip()
        if not words or len(words.split()) > 5:
            continue
        for name, (pat, _) in SECTIONS.items():
            if re.fullmatch(rf"(?:{pat})\s*:?", words, re.I):
                found.add(name)
    return found


def quality(text: str, pages: int) -> dict:
    """The overall score and what it is made of. Safe to store: no personal details."""
    heads = _headings(text)
    words = len(re.findall(r"[A-Za-z][A-Za-z+#.]*", text))
    skills = extract_resume(text)["skills_raw"]
    results = len(RESULT.findall(text))
    verbs = len(set(m.lower() for m in ACTION.findall(text)))
    links = {"github": bool(re.search(r"github\.com/\w", text, re.I)), "linkedin": bool(re.search(r"linkedin\.com/in/\w", text, re.I))}
    has_email, has_phone = bool(EMAIL_RE.search(text)), bool(PHONE_RE.search(text))

    parts = {
        "sections": sum(pts for name, (_, pts) in SECTIONS.items() if name in heads),
        "contact": 5 * has_email + 5 * has_phone,
        "skills": min(len(skills), 10) * 2,
        "length": 10 if 250 <= words <= 900 else 6 if 150 <= words <= 1300 else 2,
        "impact": (10 if results >= 3 else 5 if results else 0) + min(verbs, 5),
        "links": 5 if any(links.values()) else 0,
    }
    tips: list[str] = []
    for name in ("skills", "projects", "education", "experience"):
        if name not in heads:
            tips.append(f"Add a clear \"{SECTION_WORD[name]}\" heading. Screening software looks for it.")
    if not has_email or not has_phone:
        tips.append("Put an email address and a phone number at the top.")
    if len(skills) < 5:
        tips.append("Name your tools and skills plainly (for example Python, SQL, Excel), not only in sentences.")
    if words < 250:
        tips.append("The resume is short. Describe two or three projects: what you built, with what, and the result.")
    elif words > 900 or pages > 2:
        tips.append("Keep it to one or two pages. Cut older or less relevant lines.")
    if results < 3:
        tips.append("Show results with numbers, for example \"cut report time by 40%\" or \"used by 200 students\".")
    if verbs < 3:
        tips.append("Start project lines with action words: built, designed, tested, improved.")
    if not any(links.values()):
        tips.append("Add a GitHub or LinkedIn link so employers can see your work.")
    score = int(sum(parts.values()))
    return {"score": score, "grade": grade(score), "parts": parts, "sections": sorted(heads), "skills": skills,
            "words": words, "pages": pages, "results": results, "action_words": verbs, "links": links,
            "has_email": has_email, "has_phone": has_phone, "tips": tips[:6]}


def grade(score: int) -> str:
    return "Strong" if score >= 75 else "Fair" if score >= 50 else "Weak"


def for_listing(report: dict, need: list[str], nice: list[str] | None = None) -> dict:
    """How the resume reads for one listing: the overall score plus how many of its skills the resume names."""
    nice_set = set(nice or [])
    have = set(report.get("skills", []))
    total = sum(0.5 if s in nice_set else 1.0 for s in need) or 1.0
    got = sum(0.5 if s in nice_set else 1.0 for s in need if s in have)
    coverage = got / total if need else 1.0
    score = round(100 * (0.7 * coverage + 0.3 * report.get("score", 0) / 100))
    missing = [s for s in need if s not in have]
    tips = [f"The listing asks for {', '.join(missing[:3])}. If you know {'it' if len(missing) == 1 else 'them'}, name {'it' if len(missing) == 1 else 'them'} in the resume."] if missing else []
    return {"score": score, "grade": grade(score), "keywords_found": [s for s in need if s in have], "keywords_missing": missing,
            "coverage": round(coverage, 3), "quality": report.get("score", 0), "tips": tips + report.get("tips", [])[:3]}
