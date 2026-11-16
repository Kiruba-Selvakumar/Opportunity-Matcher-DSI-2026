"""Constants and file paths. See IMPLEMENTATION_PLAN.md section 4.1."""
import os
from pathlib import Path

SEED = 42
N_STUDENTS = 100
N_JOBS, N_TRAINING, N_MENTORS = 30, 15, 5
MESSY_SHARE = 0.30
MISSING_SHARE = 0.08
RELOCATION_COST = 10000
TOP_K = 5
LONG_HOURS = 48
WEIGHT_SIM, WEIGHT_COVERAGE = 0.6, 0.4
PENALTY_LONG_HOURS = 0.05
PENALTY_SAFETY_3 = 0.03
PENALTY_SAFETY_LOW = 0.10
# Matching v2 (IMPLEMENTATION_PLAN.md section 9.17). Each part can be switched off to get the v1 score.
V2 = {"idf": True, "related": True, "soft": True, "congestion": True, "prior": True, "training": True, "tech_sim": True}
NICE_WEIGHT = 0.5             # a nice-to-have skill counts half
SAME_CATEGORY_CREDIT = 0.2    # credit for a skill in the same area when no related pair is listed
BRANCH_FIT_MAX = 0.05
HOME_STATE_BONUS = 0.02
LOW_CGPA, LOW_CGPA_PENALTY = 6.0, 0.02
CONGESTION_FACTOR, CONGESTION_MAX = 3, 0.06   # above 3 x openings in play, lower the score by up to 0.06
PRIOR_MIN_DECISIONS, PRIOR_MAX = 5, 0.03
OPENINGS_DEFAULT = {"job": 3, "training": 25, "mentor": 5}
FIT_STRONG, FIT_GOOD = 0.6, 0.4
MIN_SHOW_SCORE = 0.2          # a match below this is not shown in the top 5 (Browse still lists it)
TRAIN_W_SIM, TRAIN_W_GAP = 0.3, 0.7   # training is scored by the gap it closes for the student's best jobs
TRAIN_JOBS = 5                # how many of the student's best jobs define their skill gap
FUZZY_CUTOFF = 0.85
EMBED_MATCH_CUTOFF = 0.75
# Matching v3 (IMPLEMENTATION_PLAN.md section 9.25). Live matching only; each term is capped and shown to staff.
V3 = {"upskill": True, "ml": True, "standing": True}
UPSKILL_MAX = 0.05            # a gap that is easy to close (related skill known, or a training teaches it) earns up to this
ML_MIN_LABELS, ML_MIN_PER_CLASS, ML_MAX = 20, 5, 0.06   # the learned nudge waits for enough staff and employer outcomes
ML_FULL_WEIGHT_AT = 100       # labels at which the learned nudge reaches its full size
STANDING_MAX, STANDING_MIN_FIELD = 0.03, 5    # rank among eligible students for a listing, once there are at least 5
CLOSING_SOON_DAYS = 7
PROGRAMS = {"placements": "Placements", "get_skills": "Get Skills"}

# DATA_ROOT can be moved (the end to end test uses a temp folder).
ROOT = Path(__file__).resolve().parents[2]


def make_paths(data_root: Path | None = None, eval_root: Path | None = None) -> dict:
    d = Path(data_root) if data_root else ROOT / "data"
    e = Path(eval_root) if eval_root else ROOT / "eval"
    return {
        "reference": d / "reference",
        "skills_vocab": d / "reference" / "skills_vocab.csv",
        "synonyms": d / "reference" / "synonyms.csv",
        "related_skills": d / "reference" / "related_skills.csv",
        "branch_fit": d / "reference" / "branch_fit.csv",
        "students_raw": d / "raw" / "students_raw.csv",
        "opportunities_raw": d / "raw" / "opportunities_raw.csv",
        "contacts": d / "private" / "contacts.csv",
        "resumes": d / "private" / "resumes",
        "students": d / "clean" / "students.json",
        "opportunities": d / "clean" / "opportunities.json",
        "cleaning_report": d / "clean" / "cleaning_report.json",
        "llm_cache": d / "derived" / "llm_cache.jsonl",
        "normalized": d / "derived" / "normalized_skills.json",
        "vectors": d / "derived" / "vectors.npz",
        "pair_scores": d / "derived" / "pair_scores.csv",
        "top5": d / "derived" / "top5.json",
        "db": d / "app.db",
        "eval_dir": e,
        "labels_template": e / "labels_template.csv",
        "labels": e / "labels.csv",
        "timing": e / "timing.csv",
        "results_json": e / "results.json",
        "results_md": e / "results.md",
    }


PATHS = make_paths(Path(os.environ["MATCHER_DATA_ROOT"]) if os.environ.get("MATCHER_DATA_ROOT") else None,
                   Path(os.environ["MATCHER_EVAL_ROOT"]) if os.environ.get("MATCHER_EVAL_ROOT") else None)
# Reference lists are committed, so they always come from the repo.
PATHS["skills_vocab"] = ROOT / "data" / "reference" / "skills_vocab.csv"
PATHS["synonyms"] = ROOT / "data" / "reference" / "synonyms.csv"
PATHS["related_skills"] = ROOT / "data" / "reference" / "related_skills.csv"
PATHS["branch_fit"] = ROOT / "data" / "reference" / "branch_fit.csv"


def set_roots(data_root: Path | str | None = None, eval_root: Path | str | None = None) -> None:
    """Point every output path at another folder (used by tests). Reference lists stay in the repo."""
    PATHS.update(make_paths(Path(data_root) if data_root else None, Path(eval_root) if eval_root else None))
    PATHS["skills_vocab"] = ROOT / "data" / "reference" / "skills_vocab.csv"
    PATHS["synonyms"] = ROOT / "data" / "reference" / "synonyms.csv"
    PATHS["related_skills"] = ROOT / "data" / "reference" / "related_skills.csv"
    PATHS["branch_fit"] = ROOT / "data" / "reference" / "branch_fit.csv"
