"""Turn messy skill text into clean fields: LLM first (optional), rules as the fallback."""
from __future__ import annotations

import re

from . import llm

SYSTEM_PROMPT = (
    "You turn messy student skill text into JSON. Use only words that appear in the text.\n"
    "Do not add skills that are not mentioned. Return JSON with keys:\n"
    '"skills_raw": list of short lowercase skill phrases,\n'
    '"projects": integer count of projects mentioned (0 if none),\n'
    '"english_level": one of "basic", "intermediate", "fluent", or null if not mentioned.'
)
SCHEMA_HINT = {"skills_raw": ["str"], "projects": 0, "english_level": "basic|intermediate|fluent|null"}

MESSY_WORDS = re.compile(r"\b(?:know|did|done|learning|little|project|ok)\b", re.IGNORECASE)

# longest phrases first so "mini project in" goes before "mini project"
FILLERS = [r"nice\s+to\s+have", r"\(?optional\)?", r"\bpreferred\b", r"\bbonus\b", r"\d+\s+projects?\s+using", r"projects?\s+using", r"mini\s+project\s+in", r"certified\s+in",
           r"english\s+ok", r"little\s+bit", r"is\s+a\s+plus", r"\bintermediate\b", r"\bknow\b", r"\bbasic\b",
           r"\bdid\b", r"\bdone\b", r"\blearning\b"]


def is_messy(text: str) -> bool:
    return bool(text) and (bool(MESSY_WORDS.search(text)) or "/" in text or "+" in text)


def count_projects(text: str) -> int:
    t = (text or "").lower()
    m = re.findall(r"(\d+)\s+projects?", t)
    if m:
        return sum(int(x) for x in m)
    return 1 if "mini project" in t else 0


NICE_MARKER = re.compile(r"is a plus|nice to have|optional|preferred|bonus", re.I)


def split_required(text: str) -> tuple[list[str], list[str]]:
    """Split a requirements text into (required, nice_to_have) phrases. A part marked "is a plus" is nice to have."""
    req, nice = [], []
    for chunk in re.split(r"[;,]", text or ""):
        (nice if NICE_MARKER.search(chunk) else req).append(chunk)
    return split_skill_phrases(", ".join(req)), split_skill_phrases(", ".join(nice))


def split_skill_phrases(text: str) -> list[str]:
    """Rule method: split, strip filler words, keep lowercase phrases."""
    t = (text or "").lower()
    t = t.replace("c++", "cpp__").replace("ci/cd", "cicd__").replace("c#", "csharp__")
    for f in FILLERS:
        t = re.sub(f, " ", t)
    t = re.sub(r"\.(?=\s|$)", ",", t)
    parts = re.split(r"[,/+;]|\band\b|\s*\(\s*\)\s*", t)
    out: list[str] = []
    for p in parts:
        p = re.sub(r"[()]", " ", p)
        p = re.sub(r"\s+", " ", p).strip(" .-")
        p = p.replace("cpp__", "c++").replace("cicd__", "ci/cd").replace("csharp__", "c#")
        if p and p not in out:
            out.append(p)
    return out


ENGLISH_WORDS = {
    "basic": "basic", "little": "basic",
    "ok": "intermediate", "good": "intermediate", "can manage": "intermediate", "intermediate": "intermediate",
    "fluent": "fluent", "very good": "fluent",
}


def parse_english(text: str) -> str | None:
    t = (text or "").strip().lower()
    return ENGLISH_WORDS.get(t)


def rule_parse(skills_text: str, english_text: str) -> dict:
    return {"skills_raw": split_skill_phrases(skills_text), "projects": count_projects(skills_text),
            "english_level": parse_english(english_text), "parse_method": "rule"}


def _valid(d: object) -> bool:
    if not isinstance(d, dict):
        return False
    if not isinstance(d.get("skills_raw"), list) or not all(isinstance(x, str) for x in d["skills_raw"]):
        return False
    if not isinstance(d.get("projects"), int) or isinstance(d.get("projects"), bool) or d["projects"] < 0:
        return False
    return d.get("english_level") in ("basic", "intermediate", "fluent", None)


def parse_student_text(skills_text: str, english_text: str, known_names: list[str] | None = None) -> dict:
    """Return {"skills_raw", "projects", "english_level", "parse_method"}."""
    fallback = rule_parse(skills_text, english_text)
    if not is_messy(skills_text):
        return fallback
    user = f'Skill text: "{skills_text}"\nEnglish text: "{english_text}"'
    result = llm.complete_json(SYSTEM_PROMPT, user, SCHEMA_HINT, known_names=known_names)
    if result is None or not _valid(result):
        return fallback
    return {"skills_raw": [s.strip().lower() for s in result["skills_raw"] if s.strip()],
            "projects": result["projects"],
            "english_level": result["english_level"] or fallback["english_level"], "parse_method": "llm"}


# ---- free-text resume extraction (rules only, so no personal details can reach an LLM) ----

def _skill_terms() -> list[tuple[str, str]]:
    """(term, canonical skill) pairs from the skill list and the synonyms."""
    from .skills import load_synonyms, load_vocab
    terms = [(s, s) for s in load_vocab()]
    for alias, canon in load_synonyms().items():
        terms += [(alias, c) for c in canon]
    return terms


def _found(text: str, term: str) -> bool:
    flags = re.IGNORECASE
    if len(term) <= 2:  # one or two letter names ("C", "ML", "JS") only count in their written case or in capitals
        flags = 0
        if term.islower():
            term = term.upper()
    return re.search(r"(?<![\w.+#])" + re.escape(term) + r"(?![\w+#])", text, flags) is not None


def extract_resume(text: str) -> dict:
    """Pull skills, CGPA, projects and an English level out of pasted resume text."""
    from .privacy import EMAIL_RE, PHONE_RE
    t = PHONE_RE.sub(" ", EMAIL_RE.sub(" ", text or ""))
    skills: list[str] = []
    for term, canon in _skill_terms():
        if canon not in skills and _found(t, term):
            skills.append(canon)
    cgpa = None
    m = (re.search(r"(?:cgpa|gpa)\s*[:\-]?\s*(\d+(?:\.\d+)?)", t, re.I)
         or re.search(r"(\d+(?:\.\d+)?)\s*/\s*10\b", t)
         or re.search(r"(\d{2}(?:\.\d+)?)\s*%", t))
    if m:
        v = float(m.group(1))
        cgpa = round(min(10.0, v / 9.5 if v > 10 else v), 1)
    lines_with_project = [ln for ln in t.splitlines() if re.search(r"\bproject", ln, re.I)]
    projects = max(count_projects(t), min(5, len(lines_with_project)))
    english = None
    if re.search(r"\bfluent (in )?english|english\s*[:\-]?\s*(fluent|native)", t, re.I):
        english = "fluent"
    elif re.search(r"english\s*[:\-]?\s*(basic|beginner)", t, re.I):
        english = "basic"
    elif re.search(r"\benglish\b", t, re.I):
        english = "intermediate"
    return {"skills_raw": skills, "projects": projects, "cgpa": cgpa, "english_level": english, "parse_method": "rule"}
