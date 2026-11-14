"""Detection rules for the five edge-case types. Used by validation (expected findings) and evaluation (precision/recall).
Each returns {entity_id: message}."""
import numpy as np
import pandas as pd
from backend.config import LOOP_DETECT_REPEATS, LOOP_MIN_GAIN


def timestamp_order_invalid(T):
    a = T["Attempt"].sort_values("attempt_id")
    out = {}
    bad = a[a.submitted_at.notna() & (a.submitted_at < a.started_at)]
    for r in bad.itertuples():
        out[r.attempt_id] = "submitted_at < started_at"
    prev = a.groupby("learner_id").started_at.shift()
    dec = a[prev.notna() & (a.started_at < prev)]
    for r in dec.itertuples():
        out.setdefault(r.attempt_id, "started_at earlier than the previous attempt in counter order")
    return out


def content_mapped_to_missing_skill(T):
    cs = T["ContentSkill"]
    bad = cs[~cs.skill_id.isin(set(T["Skill"].skill_id))]
    return {r.content_skill_id: f"skill {r.skill_id} does not exist" for r in bad.itertuples()}


def mastery_uses_future_attempt(T):
    r = T["AssessmentResult"].merge(T["Attempt"][["attempt_id", "submitted_at"]], on="attempt_id", how="left")
    bad = r[r.submitted_at.notna() & (r.computed_at < r.submitted_at)]
    return {x.result_id: "computed_at before its evidence was submitted" for x in bad.itertuples()}


def mastery_timeline(T):
    """(learner_id, skill_id, t, mastery_after) where t = submitted_at of the evidence attempt."""
    r = T["AssessmentResult"].merge(T["Attempt"][["attempt_id", "submitted_at"]], on="attempt_id")
    return r[["learner_id", "skill_id", "submitted_at", "attempt_id", "mastery_after"]].rename(columns={"submitted_at": "t"})


def prereq_violations(T, cat):
    """Recommendations whose item has a REQUIRED prerequisite below min_mastery at recommended_at."""
    recs = T["Recommendation"]
    recs = recs[recs.content_id.notna()]
    rows = []
    for r in recs[["recommendation_id", "learner_id", "content_id", "recommended_at"]].itertuples(index=False):
        it = cat.items.get(r.content_id)
        if it is None:
            continue
        t = int(r.recommended_at)
        for s, _ in it.skills:
            for p, mm in cat.required(s, t):
                rows.append((r.recommendation_id, r.learner_id, p, t, mm))
    if not rows:
        return {}
    need = pd.DataFrame(rows, columns=["recommendation_id", "learner_id", "skill_id", "t", "min_mastery"]).sort_values("t", kind="mergesort")
    tl = mastery_timeline(T).sort_values(["t", "attempt_id"], kind="mergesort")
    tl["t"] = tl["t"].astype("int64"); need["t"] = need["t"].astype("int64")
    m = pd.merge_asof(need, tl[["learner_id", "skill_id", "t", "mastery_after"]], on="t", by=["learner_id", "skill_id"], direction="backward")
    m["mastery_after"] = m["mastery_after"].fillna(0.0)
    bad = m[m.mastery_after < m.min_mastery - 1e-9]
    out = {}
    for r in bad.itertuples():
        out.setdefault(r.recommendation_id, f"{r.skill_id} needs {r.min_mastery:.2f}, had {r.mastery_after:.2f}")
    return out


def path_loops(T):
    e = T["LearningPathEvent"]
    e = e[e.event_type == "STEP_ASSIGNED"].sort_values(["path_id", "event_seq"])
    out = {}
    for pid, g in e.groupby("path_id", sort=True):
        c, m = g.content_id.tolist(), g.mastery_snapshot.astype(float).tolist()
        i = 0
        while i < len(c):
            j = i
            while j + 1 < len(c) and c[j + 1] == c[i]:
                j += 1
            run = j - i + 1
            # any window of LOOP_DETECT_REPEATS identical consecutive steps with no mastery movement is a loop
            for s in range(i, j - LOOP_DETECT_REPEATS + 2):
                w = m[s:s + LOOP_DETECT_REPEATS]
                if max(w) - min(w) < LOOP_MIN_GAIN:
                    out[pid] = f"{c[i]} assigned {run}x in a row without mastery gain"
                    break
            i = j + 1
    return out


def detect_all(T, cat):
    return {
        "RECOMMENDATION_VIOLATES_PREREQUISITE": prereq_violations(T, cat),
        "ATTEMPT_TIMESTAMP_ORDER_INVALID": timestamp_order_invalid(T),
        "CONTENT_MAPPED_TO_NONEXISTENT_SKILL": content_mapped_to_missing_skill(T),
        "MASTERY_USES_FUTURE_ATTEMPT": mastery_uses_future_attempt(T),
        "LEARNER_PATH_LOOPS_WITHOUT_PROGRESS": path_loops(T),
    }
