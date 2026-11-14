"""Step 8: validation. Hard errors vs. *labelled findings* (deliberate anomalies that the checks are expected to catch).

Outcome rules:
  - `unexpected_errors` must be 0                      (the data is otherwise clean)
  - every labelled anomaly must be observed by its catcher check (`missed_labelled` must be 0)
"""
import numpy as np
import pandas as pd
from backend.config import EVIDENCE_WEIGHT, ASSESSED
from backend.engine import ewma, mastery_level
from .config import AS_OF, TIMELINE_START
from .schema import SCHEMA, TRANSITIONS, LEAK_COLUMNS, ISSUE_TYPES
from .ids import ID_PATTERNS
from .derive import rec_outcomes, derive_paths
from . import rules

# which check names are the "expected" catchers for each ground-truth issue type
CATCHERS = {
    "RECOMMENDATION_VIOLATES_PREREQUISITE": {"rec_prerequisites_respected"},
    "ATTEMPT_TIMESTAMP_ORDER_INVALID": {"attempt_submitted_after_started", "attempt_counter_follows_time", "attempt_duration_reconciles"},
    "CONTENT_MAPPED_TO_NONEXISTENT_SKILL": {"fk:ContentSkill.skill_id->Skill.skill_id"},
    "MASTERY_USES_FUTURE_ATTEMPT": {"result_not_before_evidence"},
    "LEARNER_PATH_LOOPS_WITHOUT_PROGRESS": {"path_no_loop_without_progress"},
}


class Report:
    def __init__(self):
        self.stats, self.findings = {}, []

    def check(self, name, checked, bad):
        """bad: iterable of (entity_id, message)."""
        bad = list(bad)
        self.stats[name] = dict(rows_checked=int(checked), violations=len(bad))
        for eid, msg in bad:
            self.findings.append(dict(check=name, entity_id=str(eid), message=msg))


def _u(df, key):
    """Lookup frame keyed by PK; duplicates are reported by pk_unique, so keep the first here."""
    return df.drop_duplicates(key).set_index(key)


def _ids(df, mask, col, msg):
    return [(v, msg) for v in df.loc[mask, col]]


def _na(s):
    return s.isna()


def validate(T, gt, cat):
    R = Report()
    L, C, S, P, CI, CS = T["Learner"], T["Course"], T["Skill"], T["SkillPrerequisite"], T["ContentItem"], T["ContentSkill"]
    LP, EV, A, AR, RC = T["LearningPath"], T["LearningPathEvent"], T["Attempt"], T["AssessmentResult"], T["Recommendation"]
    # ---------------- 1. primary keys -----------------
    for name, spec in SCHEMA.items():
        df = T[name]; pk = spec["pk"][0]
        R.check(f"pk_unique:{name}", len(df), [(k, "duplicate PK") for k in df.loc[df.duplicated(pk, keep=False), pk]])
        R.check(f"pk_not_null:{name}", len(df), [(i, "null PK") for i in df.index[df[pk].isna()]])
    # ---------------- 2. ID formats -----------------
    for key, pat in ID_PATTERNS.items():
        t, c = key.split("."); s = T[t][c].astype(str)
        R.check(f"id_format:{key}", len(s), [(v, f"does not match {pat}") for v in s[~s.str.match(pat)]])
    R.check("attempt_id_embeds_learner", len(A), _ids(A, A.attempt_id.str[4:14] != A.learner_id, "attempt_id", "learner part != learner_id"))
    # ---------------- 3. foreign keys -----------------
    for name, spec in SCHEMA.items():
        pk = spec["pk"][0]
        for col in spec["cols"]:
            if col[7]:
                pt, pc = col[7].split(".")
                vals = T[name][[pk, col[0]]].dropna()
                bad = vals[~vals[col[0]].isin(set(T[pt][pc]))]
                R.check(f"fk:{name}.{col[0]}->{col[7]}", len(vals), [(r[0], f"{col[0]}={r[1]} missing in {pt}") for r in bad.itertuples(index=False)])
    # ---------------- 4. required fields & enums -----------------
    for name, spec in SCHEMA.items():
        df, pk = T[name], spec["pk"][0]
        for nm, typ, req, allowed, *_ in spec["cols"]:
            if req:
                R.check(f"required:{name}.{nm}", len(df), _ids(df, df[nm].isna(), pk, "null in required field"))
            if allowed:
                s = df[nm].dropna()
                R.check(f"enum:{name}.{nm}", len(s), [(df.loc[i, pk], f"{s[i]} not allowed") for i in s.index[~s.isin(allowed)]])
    # ---------------- 5. conditional fields -----------------
    R.check("learner_withdrawn_fields", len(L), _ids(L, (L.status == "WITHDRAWN") != L.withdrawn_at.notna(), "learner_id", "withdrawn_at iff WITHDRAWN"))
    R.check("learner_cohort_from_enrolment", len(L), _ids(L, L.cohort != L.enrolled_at.map(lambda t: f"2026-Q{(pd.Timestamp(t, unit='s').month - 1) // 3 + 1}"),
                                                          "learner_id", "cohort != quarter(enrolled_at)"))
    asd = CI.format.isin(ASSESSED)
    bad = (CI.is_assessed != asd.astype(int)) | (CI.max_score.notna() != asd) | (CI.pass_threshold_pct.notna() != asd)
    R.check("content_assessed_fields", len(CI), _ids(CI, bad, "content_id", "is_assessed/max_score/pass_threshold inconsistent with format"))
    bad = (CI.published_at.isna() != (CI.status == "DRAFT")) | (CI.retired_at.notna() != (CI.status == "RETIRED")) | (CI.retired_at <= CI.published_at)
    R.check("content_lifecycle_fields", len(CI), _ids(CI, bad, "content_id", "published/retired dates inconsistent with status"))
    prim = CS[CS.skill_id.isin(set(S.skill_id))].groupby("content_id").is_primary.sum()
    R.check("content_one_primary_skill", len(CI), [(c, f"{int(prim.get(c, 0))} primary skills") for c in CI.content_id if prim.get(c, 0) != 1])
    cmap = _u(CI, "content_id")
    a_ass = A.content_id.map(cmap.is_assessed).astype(bool)
    comp = A.status == "COMPLETED"
    bad = (A.submitted_at.notna() != comp) | (A.raw_score.notna() != (comp & a_ass)) | (A.score_pct.notna() != (comp & a_ass)) | ((A.completion_pct == 100) != comp)
    R.check("attempt_status_fields", len(A), _ids(A, bad, "attempt_id", "submitted/score/completion fields inconsistent with status"))
    scored = A.max_score.notna()
    R.check("attempt_max_score_matches_content", int(scored.sum()), _ids(A, scored & (A.max_score != A.content_id.map(cmap.max_score)), "attempt_id", "max_score != content max_score"))
    esc = RC.status == "ESCALATED"
    bad = (RC.content_id.isna() != esc) | ((RC.outcome == "ESCALATED") != esc) | ((RC.reason_code == "NO_ELIGIBLE_CONTENT") != esc)
    R.check("rec_escalation_fields", len(RC), _ids(RC, bad, "recommendation_id", "escalation fields inconsistent"))
    et = EV.event_type
    bad = ((et == "STEP_ASSIGNED") & (EV.content_id.isna() | EV.recommendation_id.isna() | EV.skill_id.isna())) | \
          ((et == "SKILL_MASTERED") & EV.skill_id.isna()) | ((et == "STATUS_CHANGED") & (EV.from_status.isna() | EV.to_status.isna())) | \
          ((et == "PATH_CREATED") & (EV.to_status != "ACTIVE"))
    R.check("path_event_type_fields", len(EV), _ids(EV, bad, "event_id", "fields inconsistent with event_type"))
    # ---------------- 6. dates and time order -----------------
    R.check("learner_enrolled_in_window", len(L), _ids(L, (L.enrolled_at < TIMELINE_START) | (L.enrolled_at > AS_OF), "learner_id", "enrolled_at outside 2026 window"))
    R.check("learner_withdrawn_after_enrolled", len(L), _ids(L, L.withdrawn_at.notna() & ((L.withdrawn_at <= L.enrolled_at) | (L.withdrawn_at > AS_OF)), "learner_id", "withdrawn_at out of order"))
    enr = _u(L, "learner_id").enrolled_at
    R.check("path_created_after_enrolment", len(LP), _ids(LP, LP.created_at < LP.learner_id.map(enr), "path_id", "path before enrolment"))
    pcr = _u(LP, "path_id")
    R.check("attempt_after_enrolment_and_path", len(A), _ids(A, (A.started_at < A.learner_id.map(enr)) | (A.started_at < A.path_id.map(pcr.created_at)) | (A.started_at > AS_OF),
                                                            "attempt_id", "attempt before enrolment/path creation or after AS_OF"))
    R.check("attempt_path_same_learner", len(A), _ids(A, A.path_id.map(pcr.learner_id) != A.learner_id, "attempt_id", "path belongs to another learner"))
    R.check("attempt_submitted_after_started", int(comp.sum()), _ids(A, A.submitted_at.notna() & (A.submitted_at < A.started_at), "attempt_id", "submitted_at < started_at"))
    As = A.sort_values("attempt_id")
    prev = As.groupby("learner_id").started_at.shift()
    R.check("attempt_counter_follows_time", len(A), _ids(As, prev.notna() & (As.started_at < prev), "attempt_id", "started before previous attempt in counter order"))
    pub, ret = A.content_id.map(cmap.published_at), A.content_id.map(cmap.retired_at)
    R.check("attempt_content_published", len(A), _ids(A, pub.isna() | (A.started_at < pub) | (ret.notna() & (A.started_at >= ret)), "attempt_id", "content not published at started_at"))
    wd = _u(L, "learner_id").withdrawn_at
    R.check("no_attempt_after_withdrawal", len(A), _ids(A, A.learner_id.map(wd).notna() & (A.started_at >= A.learner_id.map(wd)), "attempt_id", "attempt after withdrawal"))
    sub = AR.attempt_id.map(_u(A, "attempt_id").submitted_at)
    R.check("result_not_before_evidence", len(AR), _ids(AR, sub.notna() & (AR.computed_at < sub), "result_id", "computed_at earlier than evidence submitted_at"))
    R.check("rec_after_enrolment_and_path", len(RC), _ids(RC, (RC.recommended_at < RC.learner_id.map(enr)) | (RC.recommended_at < RC.path_id.map(pcr.created_at)) |
                                                       (RC.recommended_at > AS_OF) | (RC.path_id.map(pcr.learner_id) != RC.learner_id), "recommendation_id", "recommendation time/path inconsistent"))
    rc = RC[RC.content_id.notna()]
    rp, rr = rc.content_id.map(cmap.published_at), rc.content_id.map(cmap.retired_at)
    R.check("rec_content_published", len(rc), _ids(rc, rp.isna() | (rc.recommended_at < rp) | (rr.notna() & (rc.recommended_at >= rr)), "recommendation_id", "recommended unpublished content"))
    R.check("prereq_effective_dates", len(P), _ids(P, P.effective_to.notna() & (P.effective_to < P.effective_from), "prerequisite_id", "effective_to < effective_from"))
    Es = EV.sort_values(["path_id", "event_seq"])
    g = Es.groupby("path_id")
    bad = (Es.event_seq != g.cumcount() + 1) | (Es.event_at < g.event_at.shift().fillna(-1))
    R.check("path_event_sequence", len(EV), _ids(Es, bad, "event_id", "event_seq not contiguous or event_at decreasing"))
    # ---------------- 7. skill graph -----------------
    sk = _u(S, "skill_id")
    known = P[P.skill_id.isin(sk.index) & P.prerequisite_skill_id.isin(sk.index)]
    R.check("prereq_no_self_loop", len(P), _ids(P, P.skill_id == P.prerequisite_skill_id, "prerequisite_id", "self loop"))
    cc = known.skill_id.map(sk.course_id) != known.prerequisite_skill_id.map(sk.course_id)
    seqc = _u(C, "course_id").sequence_in_domain
    bad = (known.cross_course.astype(bool) != cc) | (~cc & (known.prerequisite_skill_id.map(sk.tier) >= known.skill_id.map(sk.tier))) | \
          (cc & (known.prerequisite_skill_id.map(sk.course_id).map(seqc) != known.skill_id.map(sk.course_id).map(seqc) - 1))
    R.check("prereq_points_backwards", len(known), _ids(known, bad, "prerequisite_id", "prerequisite not in a lower tier / previous course"))
    R.check("skill_graph_acyclic", len(S), [(s, "cycle") for s in _cycle_nodes(known)])
    ck = CS[CS.skill_id.isin(sk.index)]
    R.check("content_skill_same_course", len(ck), _ids(ck, ck.skill_id.map(sk.course_id) != ck.content_id.map(cmap.course_id), "content_skill_id", "skill from another course"))
    # ---------------- 8. arithmetic reconciliation -----------------
    R.check("attempt_duration_reconciles", int(comp.sum()), _ids(A, comp & (A.duration_sec != A.submitted_at - A.started_at), "attempt_id", "duration_sec != submitted_at - started_at"))
    sc = A[A.score_pct.notna()]
    R.check("attempt_score_pct_reconciles", len(sc), _ids(sc, ~np.isclose(sc.score_pct, (100 * sc.raw_score / sc.max_score).round(2)) | (sc.raw_score > sc.max_score) | (sc.raw_score < 0),
                                                        "attempt_id", "score_pct != round(100*raw/max, 2)"))
    R.check("attempt_passed_reconciles", len(sc), _ids(sc, sc.passed.astype(int) != (sc.score_pct >= sc.content_id.map(cmap.pass_threshold_pct)).astype(int), "attempt_id", "passed != score >= threshold"))
    no = As.groupby(["learner_id", "content_id"]).cumcount() + 1
    R.check("attempt_no_contiguous", len(A), _ids(As, As.attempt_no != no, "attempt_id", "attempt_no not 1..n per learner+content"))
    R.check("mastery_replay_reconciles", len(AR), _mastery_replay(A, AR, CI, CS, cat))
    R.check("assessed_attempt_has_evidence", int((comp & a_ass).sum()), _evidence_complete(A[comp & a_ass], AR, cat))
    R.check("rec_outcome_reconciles", len(RC), _rec_outcomes(RC, A))
    lnk = A[A.recommendation_id.notna()]
    rcx = _u(RC, "recommendation_id")
    R.check("attempt_rec_link_consistent", len(lnk), _ids(lnk, (lnk.recommendation_id.map(rcx.outcome_attempt_id) != lnk.attempt_id) |
                                                          (lnk.recommendation_id.map(rcx.content_id) != lnk.content_id), "attempt_id", "linked recommendation does not point back"))
    bad_paths, bad_status = _path_reconcile(T, sk)
    R.check("path_summary_reconciles", len(LP), bad_paths)
    R.check("path_status_events_reconcile", len(LP), bad_status)
    # ---------------- 9. lifecycle transitions -----------------
    st = EV[EV.to_status.notna()].sort_values(["path_id", "event_seq"])
    bad = []
    last = {}
    for r in st.itertuples(index=False):
        frm = last.get(r.path_id)
        if r.to_status not in TRANSITIONS[frm] or (r.event_type == "STATUS_CHANGED" and r.from_status != frm):
            bad.append((r.event_id, f"illegal transition {frm} -> {r.to_status}"))
        last[r.path_id] = r.to_status
    R.check("path_lifecycle_transitions", len(st), bad)
    R.check("path_status_is_last_event", len(LP), _ids(LP, LP.path_id.map(last) != LP.status, "path_id", "status != last status event"))
    R.check("path_completed_fields", len(LP), _ids(LP, LP.completed_at.notna() != (LP.status == "COMPLETED"), "path_id", "completed_at iff COMPLETED"))
    # ---------------- 10. business rules -----------------
    R.check("rec_has_reason_code", len(RC), _ids(RC, RC.reason_code.isna() | (RC.reason_code == "") | RC.rationale.isna() | (RC.rationale.str.len() < 20), "recommendation_id", "missing reason code / rationale"))
    rk = RC.sort_values(["learner_id", "recommended_at", "rank"])
    R.check("rec_rank_contiguous", len(RC), _ids(rk, rk["rank"] != rk.groupby(["learner_id", "recommended_at"]).cumcount() + 1, "recommendation_id", "rank not 1..k per decision"))
    primary = _u(CS[CS.is_primary == 1], "content_id").skill_id
    R.check("rec_skill_is_primary", len(rc), _ids(rc, rc.skill_id != rc.content_id.map(primary), "recommendation_id", "skill_id is not the item's primary skill"))
    viol = rules.prereq_violations(T, cat)
    R.check("rec_prerequisites_respected", len(rc), sorted(viol.items()))
    stp = EV[EV.event_type == "STEP_ASSIGNED"]
    R.check("step_matches_rank1_rec", len(stp), _ids(stp, (stp.recommendation_id.map(rcx.content_id) != stp.content_id) | (stp.recommendation_id.map(rcx["rank"]) != 1),
                                                     "event_id", "step does not match its rank-1 recommendation"))
    R.check("path_no_loop_without_progress", int(LP.shape[0]), sorted(rules.path_loops(T).items()))
    # ---------------- 11. duplicates -----------------
    dup = lambda df, cols, pk: [(v, f"duplicate {cols}") for v in df.loc[df.duplicated(cols, keep=False), pk]]
    R.check("duplicate_content_skill", len(CS), dup(CS, ["content_id", "skill_id"], "content_skill_id"))
    R.check("duplicate_attempt_no", len(A), dup(A, ["learner_id", "content_id", "attempt_no"], "attempt_id"))
    R.check("duplicate_prerequisite_rule", len(P), dup(P, ["skill_id", "prerequisite_skill_id", "effective_from"], "prerequisite_id"))
    R.check("duplicate_learner_course_path", len(LP), dup(LP, ["learner_id", "course_id"], "path_id"))
    R.check("duplicate_result_per_attempt_skill", len(AR), dup(AR, ["attempt_id", "skill_id"], "result_id"))
    R.check("duplicate_learner_email", len(L), dup(L, ["email"], "learner_id"))
    # ---------------- 12. ground truth integrity / no leakage -----------------
    ent = {"ATTEMPT": A.attempt_id, "ASSESSMENT_RESULT": AR.result_id, "CONTENT_SKILL": CS.content_skill_id,
           "RECOMMENDATION": RC.recommendation_id, "LEARNING_PATH": LP.path_id}
    bad = [(r.gt_id, f"{r.entity_id} not found") for r in gt.itertuples() if r.entity_id not in set(ent[r.entity_type])]
    bad += [(r.gt_id, "unknown issue_type") for r in gt.itertuples() if r.issue_type not in ISSUE_TYPES]
    R.check("ground_truth_ids_exist", len(gt), bad)
    leaks = [(f"{n}.{c}", "ground-truth style column in input table") for n, df in T.items() for c in df.columns if c in LEAK_COLUMNS]
    R.check("ground_truth_not_in_inputs", sum(len(df.columns) for df in T.values()), leaks)
    return _classify(R, gt)


def _classify(R, gt):
    label_idx = {}
    for r in gt.itertuples():
        label_idx.setdefault(r.entity_id, set()).add(r.issue_type)
    labelled, unexpected = [], []
    for f in R.findings:
        types = label_idx.get(f["entity_id"], set())
        (labelled if any(f["check"] in CATCHERS[t] for t in types) else unexpected).append(f)
    observed = {f["entity_id"] for f in labelled}
    missed = [r.entity_id for r in gt.itertuples() if r.entity_id not in observed]
    by_check = {}
    for f in labelled:
        by_check[f["check"]] = by_check.get(f["check"], 0) + 1
    return dict(status="PASS" if not unexpected and not missed else "FAIL", checks_run=len(R.stats),
                total_rows_checked=int(sum(v["rows_checked"] for v in R.stats.values())),
                unexpected_errors=len(unexpected), missed_labelled=len(missed),
                labelled_findings_observed=len(labelled), labelled_findings_by_check=dict(sorted(by_check.items())),
                checks=R.stats, unexpected_error_samples=unexpected[:25], missed_labelled_samples=missed[:25])


def _cycle_nodes(P):
    g = {}
    for r in P.itertuples(index=False):
        g.setdefault(r.skill_id, []).append(r.prerequisite_skill_id)
    color, bad = {}, set()
    for start in sorted(g):
        if color.get(start):
            continue
        stack = [(start, iter(g.get(start, ())))]
        color[start] = 1
        while stack:
            node, itr = stack[-1]
            nxt = next(itr, None)
            if nxt is None:
                color[node] = 2; stack.pop()
            elif color.get(nxt) == 1:
                bad.add(nxt)
            elif not color.get(nxt):
                color[nxt] = 1; stack.append((nxt, iter(g.get(nxt, ()))))
    return sorted(bad)


def _mastery_replay(A, AR, CI, CS, cat):
    """Recompute every mastery value from attempts alone and compare with the stored evidence rows."""
    x = AR.merge(A[["attempt_id", "submitted_at", "score_pct"]].rename(columns={"score_pct": "att_score"}), on="attempt_id", how="left")
    x = x.merge(CI[["content_id", "difficulty", "format"]], on="content_id", how="left")
    x = x.merge(CS[["content_id", "skill_id", "weight"]], on=["content_id", "skill_id"], how="left")
    x = x.sort_values(["learner_id", "skill_id", "submitted_at", "attempt_id"], kind="mergesort")
    bad, key, m, n = [], None, 0.0, 0
    for r in x.itertuples(index=False):
        if (r.learner_id, r.skill_id) != key:
            key, m, n = (r.learner_id, r.skill_id), 0.0, 0
        w = round(r.weight * EVIDENCE_WEIGHT.get(r.format, 0), 4) if r.weight == r.weight else None
        after = ewma(m, r.att_score, w, r.difficulty) if w is not None else None
        n += 1
        if (w is None or abs(r.evidence_weight - w) > 1e-9 or abs(r.mastery_before - m) > 1e-9 or after is None
                or abs(r.mastery_after - after) > 1e-9 or r.evidence_count != n or r.score_pct != r.att_score
                or r.mastery_level != mastery_level(after, n)):
            bad.append((r.result_id, f"stored {r.mastery_before}->{r.mastery_after} (n={r.evidence_count}) vs replay {m}->{after} (n={n})"))
        m = after if after is not None else m
    return bad


def _evidence_complete(Aas, AR, cat):
    have = AR.groupby("attempt_id").skill_id.apply(set).to_dict()
    bad = []
    for r in Aas[["attempt_id", "content_id"]].itertuples(index=False):
        it = cat.items.get(r.content_id)
        want = {s for s, _ in it.skills} if it else set()
        if have.get(r.attempt_id, set()) != want:
            bad.append((r.attempt_id, "evidence rows do not match mapped skills"))
    return bad


def _rec_outcomes(RC, A):
    recs = RC.rename(columns={"recommendation_id": "_key"}).to_dict("records")
    att = A[["attempt_id", "learner_id", "content_id", "started_at", "status", "score_pct", "passed"]].to_dict("records")
    for a in att:
        if a["score_pct"] != a["score_pct"]:
            a["score_pct"] = None
    exp = rec_outcomes(recs, att)
    bad = []
    for r in recs:
        e = exp[r["_key"]]
        for k, v in e.items():
            got = r[k]
            got = None if got is None or (isinstance(got, float) and got != got) else got
            if got != v and not (isinstance(v, float) and got is not None and abs(got - v) < 1e-9):
                bad.append((r["_key"], f"{k}: stored {got} vs derived {v}")); break
    return bad


def _path_reconcile(T, sk):
    LP, EV = T["LearningPath"], T["LearningPathEvent"]
    nonst = EV[EV.event_type != "STATUS_CHANGED"][["path_id", "event_type", "event_at"]].to_dict("records")
    att = T["Attempt"][["path_id", "started_at"]].to_dict("records")
    lrn = T["Learner"][["learner_id", "withdrawn_at"]].to_dict("records")
    for x in lrn:
        if x["withdrawn_at"] != x["withdrawn_at"]:
            x["withdrawn_at"] = None
        else:
            x["withdrawn_at"] = int(x["withdrawn_at"])
    spc = sk.groupby("course_id").size().to_dict()
    paths = LP[["path_id", "learner_id", "course_id", "created_at"]].to_dict("records")
    sev, summ = derive_paths(paths, nonst, att, lrn, spc)
    bad_p = []
    for r in LP.to_dict("records"):
        e = summ[r["path_id"]]
        for k, v in e.items():
            got = r[k]
            got = None if got is None or (isinstance(got, float) and got != got) else got
            num = isinstance(v, (int, float)) and isinstance(got, (int, float))
            if got != v and not (num and abs(float(got) - float(v)) < 1e-9):
                bad_p.append((r["path_id"], f"{k}: stored {got} vs derived {v}")); break
    want = {}
    for e in sev:
        want.setdefault(e["path_id"], []).append((int(e["event_at"]), e["from_status"], e["to_status"]))
    got = {}
    for r in EV[EV.event_type == "STATUS_CHANGED"].sort_values(["path_id", "event_seq"]).itertuples(index=False):
        got.setdefault(r.path_id, []).append((int(r.event_at), r.from_status, r.to_status))
    bad_s = [(p, "status events differ from derivation") for p in LP.path_id if sorted(want.get(p, [])) != sorted(got.get(p, []))]
    return bad_p, bad_s
