"""The live, in-memory picture of every student, listing and match.

It is rebuilt in small steps when something changes (a listing is approved or closed, a student edits their profile,
an application is made), so people see the effect straight away and nothing needs a restart. Every change builds new
dictionaries and swaps them in, so a request that is reading never sees a half-built state. The database is the
source of truth, so a restart loads the same picture again. Run one worker process: this state lives in memory.
"""
from __future__ import annotations

import json
import threading
from datetime import date
from pathlib import Path

import pandas as pd

from matcher import applications, db, learn, learning_plan, listings, profile_edits, relative
from matcher.config import PATHS
from matcher.embed import get_encoder, profile_vector
from matcher.explain import fill_reasons
from matcher.rank import to_top_matches, top_k
from matcher.recommend import close_the_gap, fit_label
from matcher.related import Context
from matcher.schema import MatchRow, Opportunity, Student, TopMatch
from matcher.score import build_context, finish, opp_vectors, score_pair, student_vector
from matcher import config
from matcher.skills import load_vocab, normalize_opportunity

REQUIRED = ["students", "opportunities", "normalized"]


def _expired(o: Opportunity) -> bool:
    return bool(o.apply_by) and date.fromisoformat(o.apply_by) < date.today()


class NotReady(RuntimeError):
    """A pipeline file is missing."""


class State:
    def __init__(self, base_students: dict[str, Student], pipeline_opps: dict[str, Opportunity], norm: dict, enc, contacts: dict[str, str]):
        self.lock = threading.RLock()
        self.enc = enc
        self.vocab = load_vocab()
        self.contacts = contacts
        self.base_students = base_students
        self.pipeline_opps = pipeline_opps
        self.base_norm = norm
        self.edits: dict[str, dict] = {}
        self.students: dict[str, Student] = dict(base_students)
        self.opps: dict[str, Opportunity] = dict(pipeline_opps)
        self.norm: dict = {"students": dict(norm["students"]), "opportunities": dict(norm["opportunities"])}
        self.opp_vecs: dict = {}
        self.ctx: Context | None = None
        self.rows_by_student: dict[str, list[MatchRow]] = {}
        self.rows_by_opp: dict[str, list[MatchRow]] = {}
        self._cache: dict[str, list[TopMatch]] = {}
        self.labels: dict[tuple[str, str], int] = {}
        self.reload_from_database()

    # ---------- building ----------

    def reload_from_database(self) -> None:
        """Read edits and active employer listings from the database, then rebuild everything."""
        with self.lock:
            self.edits = profile_edits.all_edits()
            opps = {oid: o for oid, o in self.pipeline_opps.items() if not _expired(o)}
            norm_o = dict(self.base_norm["opportunities"])
            for row in listings.list_all(status="active"):
                o = listings.to_opportunity(row)
                opps[o.opp_id] = o
                norm_o[o.opp_id] = normalize_opportunity(o, self.enc)
            self.opps = opps
            self._set_students()
            self.norm = {"students": self.norm["students"], "opportunities": norm_o}
            self.rebuild()

    def _set_students(self) -> None:
        students, norm_s = {}, {}
        for sid, base in self.base_students.items():
            e = {k: v for k, v in self.edits.get(sid, {}).items() if not k.startswith("_")}
            students[sid] = profile_edits.apply_edits(base, e)
            n = dict(self.base_norm["students"][sid])
            if e.get("extra_skills"):
                n["skills"] = list(dict.fromkeys(n["skills"] + e["extra_skills"]))
            norm_s[sid] = n
        self.students = students
        self.norm = {"students": norm_s, "opportunities": self.norm["opportunities"]}

    def rebuild(self) -> None:
        with self.lock:
            opps = list(self.opps.values())
            self.opp_vecs = opp_vectors(opps, self.norm, self.enc)
            self.ctx = build_context(opps, self.norm)
            self._swap(self._full_pass())

    def _full_pass(self) -> dict[str, list[MatchRow]]:
        """Score everyone in two passes: the learned nudge is trained on the first pass, and standing needs everyone's score."""
        ctx = self.ctx
        ctx.model, ctx.competition = None, None  # type: ignore[union-attr]
        by_student = {sid: self._score_student(sid) for sid in self.students}
        try:
            self.labels = learn.labels(db.list_decisions(), applications.list_apps())
        except Exception:  # no database yet: nothing to learn from
            self.labels = {}
        ctx.model = learn.train(by_student, self.labels)  # type: ignore[union-attr]
        by_student = {sid: learn.apply(rows, ctx) for sid, rows in by_student.items()}  # type: ignore[arg-type]
        ctx.competition = relative.competition(by_student)  # type: ignore[union-attr]
        return {sid: relative.apply(rows, ctx) for sid, rows in by_student.items()}  # type: ignore[arg-type]

    def _score_student(self, sid: str, skills: list[str] | None = None) -> list[MatchRow]:
        s = self.students[sid]
        skills = skills if skills is not None else self.norm["students"][sid]["skills"]
        vec = student_vector(skills, self.enc, self.ctx)  # type: ignore[arg-type]
        rows = [score_pair(s, o, skills, vec, self.norm, self.opp_vecs[o.opp_id], self.ctx) for o in self.opps.values()]  # type: ignore[arg-type]
        return finish(rows, self.norm, self.ctx, s, skills, self.opps)  # type: ignore[arg-type]

    def _swap(self, by_student: dict[str, list[MatchRow]]) -> None:
        by_opp: dict[str, list[MatchRow]] = {oid: [] for oid in self.opps}
        for rows in by_student.values():
            for r in rows:
                by_opp[r.opp_id].append(r)
        self.rows_by_student, self.rows_by_opp = by_student, by_opp
        self._cache = {}

    # ---------- small updates ----------

    def refresh_student(self, sid: str) -> None:
        """A student changed their own profile."""
        with self.lock:
            e = profile_edits.get_edits(sid)
            if e:
                self.edits[sid] = e
            else:
                self.edits.pop(sid, None)
            self._set_students()
            by_student = dict(self.rows_by_student)
            by_student[sid] = self._score_student(sid)
            self._swap(by_student)

    def refresh_load(self) -> None:
        """Applications changed: some listings are busier or quieter, and outcomes teach the learned nudge. Rescore everyone."""
        with self.lock:
            self.ctx.load = applications.load_by_listing()  # type: ignore[union-attr]
            self._swap(self._full_pass())

    def refresh_prior(self) -> None:
        """Staff made a decision, which feeds the small staff prior."""
        with self.lock:
            self.rebuild()

    def drop_expired(self) -> list[str]:
        """Take listings from the data file out of matching once their last day has passed. Posted listings close in the database."""
        with self.lock:
            gone = [oid for oid, o in self.opps.items() if oid in self.pipeline_opps and _expired(o)]
            if gone:
                self.opps = {k: v for k, v in self.opps.items() if k not in gone}
                self.norm = {"students": self.norm["students"], "opportunities": {k: v for k, v in self.norm["opportunities"].items() if k not in gone}}
                self.rebuild()
            return gone

    def sync_listing(self, oid: str) -> None:
        """A listing changed status. Put it in or take it out of matching."""
        with self.lock:
            row = listings.get(oid)
            active = row is not None and row["status"] == "active"
            if active:
                o = listings.to_opportunity(row)  # type: ignore[arg-type]
                self.opps = {**self.opps, oid: o}
                self.norm = {"students": self.norm["students"], "opportunities": {**self.norm["opportunities"], oid: normalize_opportunity(o, self.enc)}}
            elif oid in self.opps and oid not in self.pipeline_opps:
                self.opps = {k: v for k, v in self.opps.items() if k != oid}
                self.norm = {"students": self.norm["students"], "opportunities": {k: v for k, v in self.norm["opportunities"].items() if k != oid}}
            else:
                return
            self.rebuild()

    # ---------- reading ----------

    def row(self, sid: str, oid: str) -> MatchRow | None:
        return next((r for r in self.rows_by_student.get(sid, []) if r.opp_id == oid), None)

    def matches(self, sid: str) -> list[TopMatch]:
        """The top 5 for a student, with reasons, fit labels and training that closes the gap."""
        cached = self._cache.get(sid)
        if cached is not None:
            return cached
        rows = self.rows_by_student[sid]
        ms = to_top_matches(top_k(rows, min_score=config.MIN_SHOW_SCORE))
        for m in ms:
            m.gap_closers = close_the_gap(rows, self.norm, m.missing, exclude=m.opp_id) if m.type == "job" else []
            m.fit = fit_label(m.final_score, bool(m.gap_closers))
        for m in ms:
            m.apply_by = self.opps[m.opp_id].apply_by
        ms = fill_reasons(self.students[sid], ms, self.opps, self.vocab)
        self._cache[sid] = ms
        return ms

    def plan(self, sid: str, chosen: list[str] | None = None) -> dict:
        """The student's learning plan: upcoming trainings that lift their best jobs, with the lift worked out.
        chosen: the courses to plan around (the student's picks); None means the suggested plan."""
        s = self.students[sid]

        def rescore(skills: list[str], opp_ids: list[str]) -> dict[str, float]:
            vec = student_vector(skills, self.enc, self.ctx)  # type: ignore[arg-type]
            return {oid: score_pair(s, self.opps[oid], skills, vec, self.norm, self.opp_vecs[oid], self.ctx).final_score  # type: ignore[arg-type]
                    for oid in opp_ids}
        return learning_plan.plan(self.rows_by_student[sid], self.norm, self.ctx, self.opps,  # type: ignore[arg-type]
                                  self.norm["students"][sid]["skills"], rescore, chosen=chosen)


def load_state() -> State:
    missing = [k for k in REQUIRED if not Path(PATHS[k]).exists()]
    if missing:
        raise NotReady("Run make all first. Missing: " + ", ".join(missing))
    students = {d["student_id"]: Student(**d) for d in json.loads(Path(PATHS["students"]).read_text())}
    opps = {d["opp_id"]: Opportunity(**d) for d in json.loads(Path(PATHS["opportunities"]).read_text())}
    norm = json.loads(Path(PATHS["normalized"]).read_text())
    contacts = {}
    if Path(PATHS["contacts"]).exists():
        df = pd.read_csv(PATHS["contacts"], dtype=str)
        contacts = dict(zip(df["student_id"], df["name"]))
    return State(students, opps, norm, get_encoder(), contacts)
