"""Hard filters: location, budget, language, family. A pair is eligible only if none fails."""
from __future__ import annotations

from .config import RELOCATION_COST
from .schema import CheckResult, Opportunity, Student


def needs_move(student: Student, opp: Opportunity) -> bool:
    return opp.mode != "remote" and opp.city != student.college_town


def check_location(student: Student, opp: Opportunity) -> CheckResult:
    if not needs_move(student, opp):
        return CheckResult(status="pass", note="remote" if opp.mode == "remote" else "in your town")
    if "near_home_only" in student.family_limits:
        return CheckResult(status="fail", note="family wants student near home")
    if student.can_relocate is True:
        return CheckResult(status="pass", note=f"needs move to {opp.city}")
    if student.can_relocate is False:
        return CheckResult(status="fail", note=f"cannot move to {opp.city}")
    return CheckResult(status="unknown", note="relocation not confirmed")


def total_cost(student: Student, opp: Opportunity) -> int:
    return opp.upfront_cost + (RELOCATION_COST if needs_move(student, opp) else 0)


def check_budget(student: Student, opp: Opportunity) -> CheckResult:
    cost = total_cost(student, opp)
    if cost == 0:
        return CheckResult(status="pass", note="free")
    if student.budget is None:
        return CheckResult(status="unknown", note=f"budget not known, costs Rs {cost}")
    if cost <= student.budget:
        return CheckResult(status="pass", note=f"costs Rs {cost}")
    return CheckResult(status="fail", note=f"costs Rs {cost}, budget Rs {student.budget}")


def check_language(student: Student, opp: Opportunity) -> CheckResult:
    lacking = [lang for lang in opp.languages_required if lang not in student.languages]
    if lacking:
        return CheckResult(status="fail", note=f"needs {', '.join(lacking)}")
    return CheckResult(status="pass", note="")


def check_family(student: Student, opp: Opportunity) -> CheckResult:
    if "no_night_shift" in student.family_limits and opp.night_shift:
        return CheckResult(status="fail", note="night shift, family limit")
    if "safe_workplace_required" in student.family_limits and opp.safety_score <= 2:
        return CheckResult(status="fail", note=f"safety score {opp.safety_score}, family needs a safe workplace")
    return CheckResult(status="pass", note="")


def check_all(student: Student, opp: Opportunity) -> dict[str, CheckResult]:
    return {"location": check_location(student, opp), "budget": check_budget(student, opp),
            "language": check_language(student, opp), "family": check_family(student, opp)}


def is_eligible(checks: dict[str, CheckResult]) -> bool:
    return all(c.status != "fail" for c in checks.values())
