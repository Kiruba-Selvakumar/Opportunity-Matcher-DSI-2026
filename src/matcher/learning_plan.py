"""A learning plan: which trainings and mentors to take, one after another, and what each does for the student's roles.

The gap is what the student's best eligible jobs ask for and they lack (weighted like training.py). The suggested plan
picks up to three courses or mentors the student can take (eligible, so affordable and reachable), each time the one that
closes the most of what is still missing; courses come first, and a mentor fills only what no course teaches. A student
can also pick their own, in the order they want.

Picks are taken one after another: each starts at its next batch after the previous one ends (a mentor any time). So for
every role the plan knows when the student would have its missing skills ("ready by") and can check that against the
role's last day to apply. The lift is measured by scoring those jobs again with the new skills added, so "Data Analyst
Trainee: 0.52 to 0.71" is the same score staff see, not a guess. It is a preview: real matches move only when the student
adds the skill.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Callable

from . import config
from .related import Context
from .schema import MatchRow, Opportunity

MAX_STEPS = 3


def next_batch(o: Opportunity, today: date) -> date | None:
    """The next start on or after today. None for a one-off that has passed; today for mentors and courses with no date."""
    if not o.starts_on:
        return today
    d = date.fromisoformat(o.starts_on)
    if d >= today:
        return d
    if o.batch_every_weeks:
        cycles = -(-(today - d).days // (7 * o.batch_every_weeks))
        return d + timedelta(weeks=cycles * o.batch_every_weeks)
    return None


def plan(rows: list[MatchRow], norm: dict, ctx: Context, opps: dict[str, Opportunity], skills: list[str],
         rescore: Callable[[list[str], list[str]], dict[str, float]], today: date | None = None,
         chosen: list[str] | None = None) -> dict:
    """rescore(skills, opp_ids) gives each job's score with that skill list.

    chosen: the courses and mentors the student picked, in the order they want to take them. None means the suggested
    plan, ordered so the role with the nearest deadline is helped first.
    """
    today = today or date.today()
    jobs = sorted((r for r in rows if r.type == "job" and r.eligible), key=lambda r: -r.final_score)[:config.TRAIN_JOBS]
    gap: dict[str, float] = {}
    for r in jobs:
        for s in r.missing:
            gap[s] = gap.get(s, 0.0) + ctx.weight(s, False)
    empty = {"targets": [], "roles": [], "steps": [], "gap": [], "options": [], "suggested": [], "order": [],
             "custom": chosen is not None, "dropped": [], "fixes": [], "late": 0}
    if not jobs:
        return {**empty, "message": "No job fits yet, so there is no gap to plan for. Start with the checks in \"Why not?\"."}
    if not gap:
        return {**empty, "message": "The best jobs ask for nothing this student lacks. Apply now."}

    options = []
    for r in rows:
        o = opps.get(r.opp_id)
        if r.type not in ("training", "mentor") or not r.eligible or o is None:
            continue
        start = next_batch(o, today)
        teaches = [s for s in norm["opportunities"][r.opp_id]["skills"] if s in gap]
        if start is not None and teaches:
            options.append((r, o, start, teaches))

    base = rescore(skills, [j.opp_id for j in jobs])

    def lift(learned: set[str]) -> dict[str, float]:
        """Each job's score once the student has learned these skills. Only the skills a job asks for are added, so a
        course in Linux never makes the student look like a weaker data analyst. Shown as a change to the score on the
        match card, so the numbers agree with what staff and students already see."""
        out = {}
        for j in jobs:
            add = [s for s in j.missing if s in learned]
            delta = rescore(skills + add, [j.opp_id])[j.opp_id] - base[j.opp_id] if add else 0.0
            out[j.opp_id] = round(min(1.0, max(0.0, j.final_score + delta)), 3)
        return out

    deadline = {j.opp_id: (opps[j.opp_id].apply_by if j.opp_id in opps else None) for j in jobs}
    suggested = by_deadline(suggest(options, gap), jobs, deadline)
    if chosen is None:
        picks, dropped = suggested, []
    else:
        by_id = {x[0].opp_id: x for x in options}
        picks = [by_id[i] for i in dict.fromkeys(chosen) if i in by_id]   # the student's order
        dropped = [i for i in chosen if i not in by_id]                  # closed, full or no longer teaching a gap

    timed = schedule(picks, today)
    learned: set[str] = set()
    left, steps = dict(gap), []
    for (r, o, _, teaches), (start, finish) in zip(picks, timed):
        if start is None:                                                 # a one-off batch that is over by the time it is reached
            steps.append({**step(r, o, None, [], []), "no_batch": True})
            continue
        new = [s for s in teaches if s in left]
        prev = lift(learned)
        learned |= set(new)
        after = lift(learned)
        for s in new:
            left.pop(s, None)
        st = step(r, o, start, new, [{"opp_id": j.opp_id, "title": j.title, "before": prev[j.opp_id], "after": after[j.opp_id]}
                                     for j in jobs if after[j.opp_id] - prev[j.opp_id] >= 0.01], finish)
        if not new:
            st["covered_by_earlier"] = True                               # a pick whose skills an earlier pick already teaches
        steps.append(st)
    final = lift(learned)
    targets = [{"opp_id": j.opp_id, "title": j.title, "before": j.final_score, "after": final[j.opp_id], "missing": j.missing}
               for j in jobs]
    roles = [{**t, "org_name": j.org_name, "pay_lpa": _pay(opps.get(j.opp_id)), **readiness(j, picks, timed, deadline[j.opp_id])}
             for t, j in zip(targets, jobs)]
    late = [x for x in roles if x["status"] == "late"]
    closed = round(100 * (1 - sum(left.values()) / sum(gap.values())))
    if not steps:
        msg = ("No course picked yet. Tick the ones you want to see how much they help." if chosen is not None
               else "No upcoming training teaches what these jobs ask for. A mentor or self-study may help.")
    else:
        n = len(steps)
        msg = f"{n} step{'s' if n > 1 else ''}{', one after another,' if n > 1 else ''} close{'s' if n == 1 else ''} {closed}% of the gap."
    suggested_ids = {x[0].opp_id for x in suggested}
    picked_ids = {x[0].opp_id for x in picks}
    return {"targets": targets, "roles": roles, "steps": steps, "gap": sorted(gap, key=lambda s: -gap[s]),
            "still_missing": sorted(left), "message": msg, **timing(steps, today), "custom": chosen is not None,
            "dropped": dropped, "order": [x[0].opp_id for x in picks], "suggested": [x[0].opp_id for x in suggested],
            "late": len(late), "fixes": fixes(late, jobs, picks, today),
            "options": sorted(({**step(r, o, start, teaches, [], _end(o, start)), "chosen": r.opp_id in picked_ids,
                                "suggested": r.opp_id in suggested_ids} for r, o, start, teaches in options),
                              key=lambda x: (not x["suggested"], x["type"] != "training", x["starts_on"] or "", x["opp_id"]))}


def suggest(options: list, gap: dict[str, float]) -> list:
    """The suggested picks, up to three: each time the one that closes the most of what is still missing. A course on the
    schedule comes before any mentor, and a mentor only fills what no course the student can take teaches."""
    pool, left, picks = list(options), dict(gap), []
    while pool and len(picks) < MAX_STEPS:
        def closes(x) -> float:
            return sum(left.get(s, 0.0) for s in x[3])
        pool.sort(key=lambda x: (not (x[0].type == "training" and closes(x) > 0), -closes(x), x[2], x[0].upfront_cost, x[0].opp_id))
        pick = pool.pop(0)
        new = [s for s in pick[3] if s in left]
        if not new:
            break
        for s in new:
            left.pop(s, None)
        picks.append(pick)
    return picks


def _pay(o: Opportunity | None) -> float | None:
    """Pay in lakhs a year, so two roles with the same title can be told apart."""
    if o is None or o.pay_min is None or o.pay_max is None:
        return None
    return round((o.pay_min + o.pay_max) / 2 / 100000, 1)


def _end(o: Opportunity, start: date | None) -> date | None:
    return start + timedelta(weeks=o.duration_weeks) if start and o.duration_weeks else None


def schedule(picks: list, today: date) -> list[tuple[date | None, date | None]]:
    """When each pick starts and ends if they are taken one after another: each starts at its next batch on or after the
    day the previous one ends (a mentor or a course with no dates starts that day). A self-paced pick has no end, so the
    next one may start the same day. A one-off batch that is over by then gives (None, None)."""
    cursor, out = today, []
    for _, o, _, _ in picks:
        start = next_batch(o, cursor)
        finish = _end(o, start)
        out.append((start, finish))
        if start:
            cursor = finish or start
    return out


def learned_on(picks: list, timed: list) -> dict[str, date | None]:
    """The day each skill is first learned in this plan: the end of the first pick that teaches it (None if self-paced)."""
    out: dict[str, date | None] = {}
    for (_, _, _, teaches), (start, finish) in zip(picks, timed):
        if start is None:
            continue
        for s in teaches:
            out.setdefault(s, finish)
    return out


def readiness(job: MatchRow, picks: list, timed: list, apply_by: str | None) -> dict:
    """When the student would have what this role is missing, and whether that is before its last day to apply.
    Only the picks that teach this role's skills count, so a long course for another role never makes it late."""
    on = learned_on(picks, timed)
    helps = [s for s in job.missing if s in on]
    if not helps:
        return {"ready_by": None, "apply_by": apply_by, "status": "not_helped", "days_late": 0, "learns": []}
    days = [on[s] for s in helps]
    ready = None if any(d is None for d in days) else max(days)          # a self-paced step has no end date to promise
    if not apply_by:
        status, late = "no_deadline", 0
    elif ready is None:
        status, late = "unknown", 0
    else:
        late = (ready - date.fromisoformat(apply_by)).days
        status = "late" if late > 0 else "in_time"
    return {"ready_by": ready.isoformat() if ready else None, "apply_by": apply_by, "status": status,
            "days_late": max(late, 0), "learns": helps}


def by_deadline(picks: list, jobs: list[MatchRow], deadline: dict[str, str | None]) -> list:
    """Order picks so the one helping the role with the nearest last day to apply comes first. On a tie a course comes
    before a mentor (the mentor was picked to fill only what the course does not teach), then the earlier start."""
    def key(x):
        dates = [deadline[j.opp_id] for j in jobs if deadline.get(j.opp_id) and set(x[3]) & set(j.missing)]
        return (min(dates) if dates else "9999-12-31", x[0].type != "training", x[2], x[0].opp_id)
    return sorted(picks, key=key)


def fixes(late: list[dict], jobs: list[MatchRow], picks: list, today: date) -> list[dict]:
    """For each role the plan makes late, up to two changes that get it in time: take a pick that teaches its skill
    first, or drop a pick that does not help it. Only changes that really bring "ready by" on or before the deadline."""
    job_of = {j.opp_id: j for j in jobs}
    out = []
    for role in late:
        job, due = job_of[role["opp_id"]], role["apply_by"]
        ideas = [("move", x, [x] + picks[:i] + picks[i + 1:]) for i, x in enumerate(picks) if i > 0 and set(x[3]) & set(job.missing)]
        ideas += [("drop", x, picks[:i] + picks[i + 1:]) for i, x in enumerate(picks) if not set(x[3]) & set(job.missing)]
        found = []
        for kind, x, order in ideas:
            r = readiness(job, order, schedule(order, today), due)
            if r["status"] == "in_time":
                # dropping a pick can take away another role's boost: say which, so the student knows what they give up
                loses = [j.title for j in jobs if kind == "drop" and set(x[3]) & set(j.missing)
                         and not any(set(y[3]) & set(j.missing) for y in order)]
                found.append({"role": job.title, "role_id": job.opp_id, "kind": kind, "opp_id": x[0].opp_id, "title": x[0].title,
                              "order": [y[0].opp_id for y in order], "ready_by": r["ready_by"], "apply_by": due, "loses": loses})
            if len(found) == 2:
                break
        out += found
    return out


def step(r: MatchRow, o: Opportunity, start: date | None, teaches: list[str], unlocks: list[dict], end: date | None = None) -> dict:
    """One course or mentor in a plan, with when it runs and how long it takes: weeks, hours a week and about how many
    hours in all. any_time: it has no batch dates, so it can start whenever the step before it ends."""
    weeks = o.duration_weeks
    return {"opp_id": r.opp_id, "title": r.title, "org_name": r.org_name, "type": r.type, "mode": r.mode, "city": r.city,
            "cost": r.upfront_cost, "starts_on": start.isoformat() if start else None, "ends_on": end.isoformat() if end else None,
            "any_time": not o.starts_on, "weeks": weeks,
            "hours_per_week": o.hours_per_week, "total_hours": weeks * o.hours_per_week if weeks else None,
            "self_paced": not weeks, "teaches": teaches, "unlocks": unlocks}


def timing(steps: list[dict], today: date) -> dict:
    """How long the whole plan takes, one step after another: the day the last step ends, the weeks from today until
    then, and the hours of the steps with a set length. Self-paced steps have no end, and the plan says so."""
    ends = [s["ends_on"] for s in steps if s["ends_on"]]
    finish = max(ends) if ends else None
    return {"finish_by": finish,
            "weeks_total": -(-(date.fromisoformat(finish) - today).days // 7) if finish else None,
            "hours_total": sum(s["total_hours"] for s in steps if s["total_hours"]) or None,
            "open_ended": sum(1 for s in steps if s["self_paced"])}
