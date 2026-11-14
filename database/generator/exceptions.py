"""Exception queue: cases the workflow routes to a person instead of handling automatically.

Built only from input tables and detection rules (never from ground truth), so it is what an
operational system would actually see.
"""
import pandas as pd
from backend.config import PASS_PCT
from .config import AS_OF, iso
from . import rules

COLUMNS = ["exception_id", "exception_type", "owner_role", "entity_type", "entity_id", "learner_id", "detected_at", "detail", "recommended_action"]
DQ_ACTION = {
    "RECOMMENDATION_VIOLATES_PREREQUISITE": ("RECOMMENDATION", "Withdraw recommendation; re-run engine with prerequisite check"),
    "ATTEMPT_TIMESTAMP_ORDER_INVALID": ("ATTEMPT", "Quarantine attempt; exclude from mastery and outcomes until corrected"),
    "CONTENT_MAPPED_TO_NONEXISTENT_SKILL": ("CONTENT_SKILL", "Reject mapping; ask content team for the correct skill"),
    "MASTERY_USES_FUTURE_ATTEMPT": ("ASSESSMENT_RESULT", "Recompute mastery as of the stamped time"),
    "LEARNER_PATH_LOOPS_WITHOUT_PROGRESS": ("LEARNING_PATH", "Escalate to instructor; enforce loop guard"),
}


def build_exception_queue(T, cat):
    rows = []
    A, AR, RC, LP = T["Attempt"], T["AssessmentResult"], T["Recommendation"], T["LearningPath"]
    for r in RC[RC.status == "ESCALATED"].itertuples(index=False):
        rows.append(("ESCALATED_RECOMMENDATION", "INSTRUCTOR", "RECOMMENDATION", r.recommendation_id, r.learner_id, r.recommended_at,
                     r.rationale, "Assign an activity manually or unblock content"))
    # three consecutive failed assessments on the same skill -> instructor review
    x = AR.merge(A[["attempt_id", "submitted_at"]], on="attempt_id").sort_values(["learner_id", "skill_id", "submitted_at", "attempt_id"])
    run, key = 0, None
    for r in x.itertuples(index=False):
        if (r.learner_id, r.skill_id) != key:
            key, run = (r.learner_id, r.skill_id), 0
        run = run + 1 if r.score_pct < PASS_PCT else 0
        if run == 3:
            rows.append(("REMEDIATION_REVIEW", "INSTRUCTOR", "SKILL", r.skill_id, r.learner_id, r.submitted_at,
                         f"3 consecutive failed assessments; mastery {r.mastery_after:.2f}", "Review misconceptions; offer tutoring"))
    # skills with no published content at AS_OF
    for sid in sorted(cat.skills):
        items = [cat.items[c] for c in cat.skill_items.get(sid, [])]
        if not any(cat.available(it, AS_OF) for it in items):
            started = AR[AR.skill_id == sid].learner_id.nunique()
            rows.append(("CONTENT_COVERAGE_GAP", "ACADEMIC_ADMIN", "SKILL", sid, None, AS_OF,
                         f"no published content for '{cat.skills[sid]['name']}'; {started} learners have evidence on it",
                         "Publish replacement content"))
    for r in LP[LP.status == "STALLED"].itertuples(index=False):
        rows.append(("STALLED_PATH", "SUPPORT_STAFF", "LEARNING_PATH", r.path_id, r.learner_id, r.status_changed_at,
                     f"no attempt for 30+ days; progress {r.progress_pct}%", "Send re-engagement outreach"))
    det = rules.detect_all(T, cat)
    lrn_of = {"RECOMMENDATION": RC.set_index("recommendation_id").learner_id, "ATTEMPT": A.set_index("attempt_id").learner_id,
              "ASSESSMENT_RESULT": AR.set_index("result_id").learner_id, "LEARNING_PATH": LP.set_index("path_id").learner_id}
    for typ in sorted(det):
        etype, action = DQ_ACTION[typ]
        for eid, msg in sorted(det[typ].items()):
            lid = lrn_of[etype].get(eid) if etype in lrn_of else None
            rows.append(("DATA_QUALITY:" + typ, "PLATFORM_ADMIN", etype, eid, lid, AS_OF, msg, action))
    df = pd.DataFrame(rows, columns=COLUMNS[1:])
    df["detected_at"] = df.detected_at.map(lambda t: iso(int(t)))
    df = df.sort_values(["exception_type", "entity_id"], kind="mergesort").reset_index(drop=True)
    df.insert(0, "exception_id", [f"EXC-{i + 1:06d}" for i in range(len(df))])
    return df
