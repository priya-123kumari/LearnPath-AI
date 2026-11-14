"""Mastery model + rule-based recommender.

Backend business logic. Also used by the database-tier generator (to simulate learners who follow recommendations), the validator (to
re-derive every stored value) and the backend API (live recommendations). Pure Python, deterministic,
no randomness and no wall-clock: the same attempts and the same as-of time always give the same answer.

Times are integer epoch seconds (UTC).
"""
from collections import namedtuple, Counter
from .config import (DAY, MASTERY_ALPHA, MASTERED_AT, PROFICIENT_AT, REMEDIATE_BELOW, SPACED_REVIEW_DAYS,
                     LOOP_GUARD_REPEATS, LOOP_MIN_GAIN, TOP_K, PASS_PCT, UNLOCK_AT, parse_iso, EVIDENCE_WEIGHT, ASSESSED, REASON_CODES)

Item = namedtuple("Item", "content_id course_id title format difficulty assessed max_score status published_at retired_at skills primary")


def mastery_level(m, evidence):
    if evidence == 0:
        return "NOT_STARTED"
    return "MASTERED" if m >= MASTERED_AT else "PROFICIENT" if m >= PROFICIENT_AT else "DEVELOPING"


def ewma(before, score_pct, weight, difficulty):
    """One mastery update. Harder items count slightly more; result rounded to 4 dp so replays are exact."""
    s_eff = min(1.0, (score_pct / 100.0) * (0.8 + 0.05 * difficulty))
    return round(before + MASTERY_ALPHA * weight * (s_eff - before), 4)


def target_difficulty(m):
    return max(1, min(5, 1 + int(round(4 * m))))


def _t(v):
    if v is None:
        return None
    if isinstance(v, str):
        return parse_iso(v)
    if isinstance(v, float) and v != v:
        return None
    return int(v)


def _day_start(v):
    t = _t(v) if not (isinstance(v, str) and len(v) == 10) else parse_iso(v + "T00:00:00Z")
    return t


def _day_end(v):
    s = _day_start(v)
    return None if s is None else s + DAY - 1


class Catalog:
    """Read-only view of skills, prerequisite rules and content used for eligibility decisions."""

    def __init__(self, skills, prereqs, items):
        self.skills = skills          # skill_id -> dict(course_id, tier, topic, name)
        self.prereqs = prereqs        # skill_id -> [(prereq_skill_id, min_mastery, eff_from, eff_to)]  REQUIRED rules only
        self.items = items            # content_id -> Item
        self.course_items, self.skill_items, self.course_skills = {}, {}, {}
        for cid in sorted(items):
            it = items[cid]
            self.course_items.setdefault(it.course_id, []).append(cid)
            for s, _ in it.skills:
                self.skill_items.setdefault(s, []).append(cid)
        for sid in sorted(skills):
            self.course_skills.setdefault(skills[sid]["course_id"], []).append(sid)

    @classmethod
    def from_tables(cls, T):
        """T: dict of DataFrames (generator tables or rows read back from SQLite)."""
        sk = T["Skill"]
        skills = {r.skill_id: dict(course_id=r.course_id, tier=int(r.tier), topic=r.topic, name=r.skill_name)
                  for r in sk.itertuples(index=False)}
        prereqs = {}
        for r in T["SkillPrerequisite"].sort_values("prerequisite_id").itertuples(index=False):
            if r.relation_type != "REQUIRED":
                continue
            to = r.effective_to if isinstance(r.effective_to, str) and r.effective_to else None
            prereqs.setdefault(r.skill_id, []).append((r.prerequisite_skill_id, float(r.min_mastery),
                                                       _day_start(r.effective_from), _day_end(to) if to else None))
        maps = {}
        for r in T["ContentSkill"].sort_values(["content_id", "is_primary", "content_skill_id"], ascending=[True, False, True]).itertuples(index=False):
            if r.skill_id in skills:                       # a mapping to an unknown skill is ignored (and flagged by validation)
                maps.setdefault(r.content_id, []).append((r.skill_id, float(r.weight), int(r.is_primary)))
        items = {}
        for r in T["ContentItem"].itertuples(index=False):
            m = maps.get(r.content_id, [])
            if not m:
                continue
            prim = next((s for s, _, p in m if p), m[0][0])
            ms = r.max_score
            items[r.content_id] = Item(r.content_id, r.course_id, r.title, r.format, int(r.difficulty), r.format in ASSESSED,
                                       None if ms is None or ms != ms else int(ms), r.status,
                                       _t(r.published_at), _t(r.retired_at), tuple((s, w) for s, w, _ in m), prim)
        return cls(skills, prereqs, items)

    def available(self, it, t):
        return it.published_at is not None and it.published_at <= t and (it.retired_at is None or t < it.retired_at)

    def required(self, skill, t):
        return [(p, mm) for p, mm, f, to in self.prereqs.get(skill, ()) if f <= t and (to is None or t <= to)]

    def unmet(self, it, mastery, t):
        """REQUIRED prerequisite rules of the item's skills that are not yet met: [(prereq_skill, min, have)]."""
        out = []
        for s, _ in it.skills:
            for p, mm in self.required(s, t):
                have = mastery.get(p, 0.0)
                if have < mm:
                    out.append((p, mm, have))
        return out

    def rules_checked(self, it, t):
        return sum(len(self.required(s, t)) for s, _ in it.skills)


class LearnerState:
    """Everything the recommender is allowed to know about a learner at a point in time (no future data)."""
    __slots__ = ("mastery", "evidence", "last_practiced", "item_stats", "steps", "total_evidence")

    def __init__(self):
        self.mastery, self.evidence, self.last_practiced = {}, {}, {}
        self.item_stats = {}       # content_id -> [attempts, passes, fails]
        self.steps = {}            # path_id -> {content_id: [mastery at each rank-1 assignment]}
        self.total_evidence = 0

    def record_step(self, path_id, content_id, skill_id):
        self.steps.setdefault(path_id, {}).setdefault(content_id, []).append(self.mastery.get(skill_id, 0.0))

    def apply_attempt(self, cat, it, status, score_pct, passed, t_submit):
        """Update state with one attempt; returns the AssessmentResult evidence rows it produces."""
        st = self.item_stats.setdefault(it.content_id, [0, 0, 0])
        st[0] += 1
        if status != "COMPLETED" or not it.assessed or score_pct is None:
            return []
        st[1 if passed else 2] += 1
        out = []
        for s, w in it.skills:
            weight = round(w * EVIDENCE_WEIGHT[it.format], 4)
            before = self.mastery.get(s, 0.0)
            after = ewma(before, score_pct, weight, it.difficulty)
            n = self.evidence.get(s, 0) + 1
            self.mastery[s], self.evidence[s], self.last_practiced[s] = after, n, t_submit
            self.total_evidence += 1
            out.append(dict(skill_id=s, evidence_weight=weight, mastery_before=before, mastery_after=after,
                            evidence_count=n, mastery_level=mastery_level(after, n)))
        return out


def replay(cat, attempts, as_of=None):
    """Rebuild a LearnerState from attempt rows (dicts with content_id, status, score_pct, passed, submitted_at/started_at).
    Only attempts submitted at or before as_of are used, ordered by (submitted_at, attempt_id): this is the
    reproducible mastery calculation and the guard against future-attempt leakage."""
    st = LearnerState()
    rows = []
    for a in attempts:
        t = _t(a.get("submitted_at")) if a.get("status") == "COMPLETED" else _t(a.get("started_at"))
        if t is None or (as_of is not None and t > as_of):
            continue
        rows.append((t, a["attempt_id"], a))
    rows.sort(key=lambda x: (x[0], x[1]))
    for t, _, a in rows:
        it = cat.items.get(a["content_id"])
        if it is None:
            continue
        sp = a.get("score_pct")
        sp = None if sp is None or (isinstance(sp, float) and sp != sp) else float(sp)
        st.apply_attempt(cat, it, a["status"], sp, bool(a.get("passed")) if sp is not None else False, t)
    return st


def _rationale(reason, cat, it, m, n, td, nrules, extra=""):
    sk = cat.skills[it.primary]["name"]
    base = f"{REASON_CODES[reason]}. Skill '{sk}' mastery {m:.2f} from {n} evidence; item difficulty {it.difficulty} vs target {td}; "
    base += f"{nrules} prerequisite rule(s) met" if nrules else "no prerequisite rules"
    return base + (f"; {extra}" if extra else "") + "."


def recommend(cat, st, paths, t, k=TOP_K, explain=False):
    """Rank next activities for one learner at time t.

    paths: [(path_id, course_id)] of the learner's open paths (ACTIVE or STALLED), oldest first.
    Returns dict(recs=[...], excluded={code: count}, exclusions=[...] if explain, escalated=bool).
    Decision order per item: published? -> prerequisites met? -> mastered/passed? -> loop guard -> reason + score.
    """
    if not paths:
        return dict(recs=[], excluded={}, exclusions=[], escalated=False)
    excluded, detail = Counter(), []
    active_courses = {c for _, c in paths}
    cand = {}                      # content_id -> (score, reason, path_id, m, n, td, extra)
    blocked = {}                   # out-of-course prerequisite skill -> path_id that needs it

    def exclude(code, it, why=""):
        excluded[code] += 1
        if explain:
            detail.append(dict(content_id=it.content_id, skill_id=it.primary, code=code, detail=why))

    def evaluate(it, path_id, gap):
        if not cat.available(it, t):
            return exclude("NOT_PUBLISHED", it, it.status)
        un = cat.unmet(it, st.mastery, t)
        if un:
            for p, mm, have in un:
                if cat.skills[p]["course_id"] not in active_courses:
                    blocked.setdefault(p, path_id)
            return exclude("PREREQ_NOT_MET", it, "; ".join(f"{p} needs {mm:.2f}, has {have:.2f}" for p, mm, have in un))
        p = it.primary
        m, n = st.mastery.get(p, 0.0), st.evidence.get(p, 0)
        stats = st.item_stats.get(it.content_id, (0, 0, 0))
        hist = st.steps.get(path_id, {}).get(it.content_id, ())
        if sum(1 for v in hist if m - v < LOOP_MIN_GAIN) >= LOOP_GUARD_REPEATS:
            return exclude("LOOP_GUARD", it, f"assigned {len(hist)}x without mastery gain")
        td = target_difficulty(m)
        fit = 1 - abs(it.difficulty - td) / 4
        tier = cat.skills[p]["tier"]
        if all(st.mastery.get(s, 0.0) >= MASTERED_AT for s, _ in it.skills):
            last = st.last_practiced.get(p)
            if it.assessed and last is not None and t - last >= SPACED_REVIEW_DAYS * DAY:
                reason, score = "SPACED_REVIEW", 0.40 + 0.1 * fit
            elif it.difficulty >= 4 and stats[1] == 0:
                reason, score = "STRETCH_CHALLENGE", 0.35 + 0.05 * it.difficulty / 5
            else:
                return exclude("ALREADY_MASTERED", it)
        elif stats[1] and m >= UNLOCK_AT:
            return exclude("ALREADY_PASSED", it, "passed and skill already strong enough to unlock dependents")
        else:
            if gap:
                reason = "PREREQ_GAP_FILL"
            elif st.total_evidence == 0:
                reason = "COLD_START_DIAGNOSTIC"
            elif n >= 2 and m < REMEDIATE_BELOW:
                reason = "REMEDIATE_LOW_MASTERY"
            elif n == 0:
                reason = "NEXT_IN_SEQUENCE"
            else:
                reason = "CONTINUE_PRACTICE"
            score = 0.45 * (1 - m) + 0.30 * fit + 0.10 * it.assessed + 0.10 * (5 - tier) / 4 - 0.08 * min(stats[2], 3) - 0.10 * min(stats[1], 2)
            if reason == "COLD_START_DIAGNOSTIC":
                score = 0.60 + 0.20 * it.assessed - 0.10 * (it.difficulty - 1)
            elif reason == "PREREQ_GAP_FILL":
                score += 0.15
            elif reason == "REMEDIATE_LOW_MASTERY" and it.difficulty > td:
                score -= 0.20
        cand[it.content_id] = (round(score, 4), reason, path_id, m, n, td)

    for path_id, course in paths:
        for cid in cat.course_items.get(course, ()):
            evaluate(cat.items[cid], path_id, False)
    # gap fill: walk back through unmet out-of-course prerequisites until eligible content is found
    seen, frontier, depth = set(), dict(blocked), 0
    while frontier and depth < 6:
        nxt = {}
        for skill in sorted(frontier):
            seen.add(skill)
            before = set(blocked)
            for cid in cat.skill_items.get(skill, ()):
                if cid not in cand:
                    evaluate(cat.items[cid], frontier[skill], True)
            for s in set(blocked) - before - seen:
                nxt[s] = frontier[skill]
        frontier, depth = nxt, depth + 1

    ranked = sorted(cand.items(), key=lambda kv: (-kv[1][0], kv[0]))
    recs, per_skill = [], Counter()
    for cid, (score, reason, path_id, m, n, td) in ranked:
        it = cat.items[cid]
        if per_skill[it.primary] >= 2:
            continue
        per_skill[it.primary] += 1
        nrules = cat.rules_checked(it, t)
        recs.append(dict(path_id=path_id, content_id=cid, skill_id=it.primary, rank=len(recs) + 1, score=score, reason_code=reason,
                         rationale=_rationale(reason, cat, it, m, n, td, nrules), mastery_snapshot=round(m, 4),
                         target_difficulty=td, prereqs_checked=nrules))
        if len(recs) == k:
            break
    escalated = not recs
    if escalated:
        recs = [dict(path_id=paths[0][0], content_id=None, skill_id=None, rank=1, score=None, reason_code="NO_ELIGIBLE_CONTENT",
                     rationale=f"{REASON_CODES['NO_ELIGIBLE_CONTENT']}. Excluded: " +
                               ", ".join(f"{c}={v}" for c, v in sorted(excluded.items())) + ".",
                     mastery_snapshot=None, target_difficulty=None, prereqs_checked=0)]
    return dict(recs=recs, excluded=dict(sorted(excluded.items())), exclusions=detail, escalated=escalated)


def passed_of(score_pct):
    return score_pct is not None and score_pct >= PASS_PCT
