"""Evaluation metrics.

1. detection quality of the anomaly rules against ground truth (precision / recall)
2. recommendation quality on a TEMPORAL split: state is rebuilt from attempts before the cutoff only, the
   engine recommends at the cutoff, and the next 30 days of attempts are the test set (vs. a popularity baseline)
3. mastery quality: does mastery at the cutoff predict passing in the test window (AUC), and how close is
   the final estimate to the hidden true mastery (ground-truth labels)
4. historical outcomes by reason code and realism statistics of the generated data
"""
import numpy as np
import pandas as pd
from backend.engine import replay, recommend
from backend.config import MASTERED_AT, PROFICIENT_AT
from .config import TEMPORAL_CUTOFF, TEST_WINDOW_DAYS, DAY, iso
from .schema import ISSUE_TYPES
from . import rules


def detection_metrics(T, gt, cat):
    det = rules.detect_all(T, cat)
    out = {}
    for typ in ISSUE_TYPES:
        truth = set(gt[gt.issue_type == typ].entity_id); d = set(det.get(typ, {}))
        tp, fp, fn = len(truth & d), len(d - truth), len(truth - d)
        out[typ] = dict(ground_truth=len(truth), detected=len(d), true_positive=tp, false_positive=fp, false_negative=fn,
                        precision=round(tp / (tp + fp), 4) if tp + fp else None, recall=round(tp / (tp + fn), 4) if tp + fn else None)
    return out


def _auc(score, label):
    score, label = np.asarray(score, float), np.asarray(label, int)
    pos, neg = label.sum(), len(label) - label.sum()
    if not pos or not neg:
        return None
    ranks = pd.Series(score).rank(method="average").to_numpy()
    return round(float((ranks[label == 1].sum() - pos * (pos + 1) / 2) / (pos * neg)), 4)


def temporal_evaluation(T, cat, max_learners=3000):
    cut, end = TEMPORAL_CUTOFF, TEMPORAL_CUTOFF + TEST_WINDOW_DAYS * DAY
    A = T["Attempt"]
    train, test = A[A.started_at < cut], A[(A.started_at >= cut) & (A.started_at < end)]
    LP = T["LearningPath"]; L = T["Learner"].set_index("learner_id")
    learners = sorted(set(train.learner_id) & set(test.learner_id))
    if len(learners) > max_learners:                              # deterministic, evenly spaced sample
        step = len(learners) / max_learners
        learners = [learners[int(i * step)] for i in range(max_learners)]
    tr_by = {k: g.to_dict("records") for k, g in train[train.learner_id.isin(learners)].groupby("learner_id")}
    te_by = {k: g.sort_values("started_at") for k, g in test[test.learner_id.isin(learners)].groupby("learner_id")}
    steps = T["LearningPathEvent"]
    steps = steps[(steps.event_type == "STEP_ASSIGNED") & (steps.event_at < cut)].merge(LP[["path_id", "learner_id"]], on="path_id")
    st_by = {k: g for k, g in steps[steps.learner_id.isin(learners)].groupby("learner_id")}
    # popularity baseline: most attempted items per course in the training period
    pop = train.merge(T["ContentItem"][["content_id", "course_id"]], on="content_id").groupby(["course_id", "content_id"]).size().reset_index(name="n")
    pop = pop.sort_values(["course_id", "n", "content_id"], ascending=[True, False, True])
    pop_by = {c: g.content_id.tolist() for c, g in pop.groupby("course_id")}
    paths_by = {k: g for k, g in LP.groupby("learner_id")}
    E = dict(engine=dict(n=0, hit=0, first=0, viol=0, recs=0, reasons=0, rows=0, pass_n=0, pass_k=0),
             popularity=dict(n=0, hit=0, first=0, viol=0, recs=0, pass_n=0, pass_k=0))
    other = dict(n=0, k=0)
    auc_s, auc_l, bucket = [], [], {}
    reason_mix = {}
    for lid in learners:
        wd = L.at[lid, "withdrawn_at"]
        if wd == wd and wd is not None and wd <= cut:
            continue
        ps = paths_by[lid]
        ps = ps[(ps.created_at < cut) & ~(ps.completed_at.notna() & (ps.completed_at <= cut))].sort_values("created_at")
        if ps.empty:
            continue
        st = replay(cat, tr_by.get(lid, []), as_of=cut)
        if lid in st_by:                                          # loop-guard history known at the cutoff
            for r in st_by[lid].sort_values("event_seq").itertuples(index=False):
                st.steps.setdefault(r.path_id, {}).setdefault(r.content_id, []).append(float(r.mastery_snapshot))
        open_paths = list(zip(ps.path_id, ps.course_id))
        res = recommend(cat, st, open_paths, cut)
        eng = [r["content_id"] for r in res["recs"] if r["content_id"]]
        popl = []
        for _, c in open_paths:
            for x in pop_by.get(c, []):
                if x not in popl and cat.items.get(x) is not None and cat.available(cat.items[x], cut):
                    popl.append(x)
                if len(popl) >= 3:
                    break
        popl = popl[:3]
        te = te_by[lid]
        firsts = te.drop_duplicates("content_id")
        tried = set(te.content_id)
        first_item = te.content_id.iloc[0]
        for r in res["recs"]:
            reason_mix[r["reason_code"]] = reason_mix.get(r["reason_code"], 0) + 1
        for name, lst in (("engine", eng), ("popularity", popl)):
            e = E[name]
            e["n"] += 1; e["recs"] += len(lst)
            e["hit"] += bool(tried & set(lst)); e["first"] += first_item in lst
            e["viol"] += sum(1 for x in lst if cat.unmet(cat.items[x], st.mastery, cut))
            sc = firsts[firsts.content_id.isin(lst) & firsts.score_pct.notna()]
            e["pass_n"] += len(sc); e["pass_k"] += int(sc.passed.sum())
        E["engine"]["reasons"] += sum(1 for r in res["recs"] if r["reason_code"])
        E["engine"]["rows"] += len(res["recs"])
        sc = firsts[~firsts.content_id.isin(eng) & firsts.score_pct.notna()]
        other["n"] += len(sc); other["k"] += int(sc.passed.sum())
        for r in firsts[firsts.score_pct.notna()].itertuples(index=False):
            it = cat.items.get(r.content_id)
            if it is None:
                continue
            m = st.mastery.get(it.primary, 0.0)
            auc_s.append(m); auc_l.append(int(r.passed))
            b = "MASTERED" if m >= MASTERED_AT else "PROFICIENT" if m >= PROFICIENT_AT else "DEVELOPING" if st.evidence.get(it.primary) else "NOT_STARTED"
            bucket.setdefault(b, [0, 0]); bucket[b][0] += 1; bucket[b][1] += int(r.passed)
    out = dict(cutoff=iso(cut), test_window_end=iso(end), train_attempts=int(len(train)), test_attempts=int(len(test)),
               train_max_started=iso(int(train.started_at.max())) if len(train) else None,
               test_min_started=iso(int(test.started_at.min())) if len(test) else None,
               split_is_temporal=bool(len(train) == 0 or len(test) == 0 or train.started_at.max() < test.started_at.min()),
               learners_evaluated=E["engine"]["n"])
    for name, e in E.items():
        out[name] = dict(hit_rate_at_3=round(e["hit"] / e["n"], 4) if e["n"] else None,
                         next_item_match_rate=round(e["first"] / e["n"], 4) if e["n"] else None,
                         prerequisite_violation_rate=round(e["viol"] / e["recs"], 4) if e["recs"] else None,
                         pass_rate_on_recommended_items=round(e["pass_k"] / e["pass_n"], 4) if e["pass_n"] else None,
                         scored_attempts_on_recommended=e["pass_n"])
    out["engine"]["reason_code_coverage"] = round(E["engine"]["reasons"] / E["engine"]["rows"], 4) if E["engine"]["rows"] else None
    out["engine"]["reason_mix_at_cutoff"] = dict(sorted(reason_mix.items()))
    out["pass_rate_on_non_recommended_items"] = round(other["k"] / other["n"], 4) if other["n"] else None
    out["mastery_at_cutoff_predicts_pass_auc"] = _auc(auc_s, auc_l)
    out["pass_rate_by_mastery_level_at_cutoff"] = {k: dict(attempts=v[0], pass_rate=round(v[1] / v[0], 4)) for k, v in sorted(bucket.items())}
    return out


def mastery_vs_truth(T, true_mastery):
    last = T["AssessmentResult"].sort_values(["learner_id", "skill_id", "evidence_count"]).groupby(["learner_id", "skill_id"]).tail(1)
    j = last.merge(true_mastery, on=["learner_id", "skill_id"], how="inner")
    if len(j) < 3:
        return {}
    j3 = j[j.evidence_count >= 3]
    return dict(pairs=int(len(j)), pearson_r=round(float(np.corrcoef(j.mastery_after, j.true_mastery)[0, 1]), 4),
                mean_abs_error=round(float((j.mastery_after - j.true_mastery).abs().mean()), 4),
                pearson_r_3plus_evidence=round(float(np.corrcoef(j3.mastery_after, j3.true_mastery)[0, 1]), 4) if len(j3) > 2 else None,
                mean_abs_error_3plus_evidence=round(float((j3.mastery_after - j3.true_mastery).abs().mean()), 4) if len(j3) else None)


def outcomes_by_reason(T):
    r = T["Recommendation"]
    out = {}
    for code, g in r.groupby("reason_code"):
        closed = g[g.status.isin(["ACCEPTED", "EXPIRED"])]
        scored = g[g.outcome.isin(["COMPLETED_PASS", "COMPLETED_FAIL"])]
        out[code] = dict(recommendations=int(len(g)), acceptance_rate=round(float((closed.status == "ACCEPTED").mean()), 4) if len(closed) else None,
                         pass_rate_when_scored=round(float((scored.outcome == "COMPLETED_PASS").mean()), 4) if len(scored) else None,
                         mean_outcome_score_pct=round(float(g.outcome_score_pct.mean()), 2) if g.outcome_score_pct.notna().any() else None)
    return out


def distribution_metrics(T, cat):
    A, L, R, CI = T["Attempt"], T["Learner"], T["Recommendation"], T["ContentItem"]
    per = A.groupby("learner_id").size().reindex(L.learner_id, fill_value=0)
    q = lambda x: {k: round(float(v), 2) for k, v in x.describe(percentiles=[.05, .25, .5, .75, .95]).items()}
    sc = A[A.score_pct.notna()]
    last = T["AssessmentResult"].sort_values("evidence_count").groupby(["learner_id", "skill_id"]).tail(1)
    gaps = prereq_gap_attempts(T, cat)
    return dict(
        learners=int(len(L)), cold_start_learners=int((per == 0).sum()), low_activity_learners_1_to_5=int(per.between(1, 5).sum()),
        withdrawn_learners=int((L.status == "WITHDRAWN").sum()), prior_level_mix=L.prior_level.value_counts().to_dict(),
        attempts=int(len(A)), attempts_per_learner=q(per), repeated_attempt_share=round(float((A.attempt_no > 1).mean()), 4),
        abandoned_share=round(float((A.status == "ABANDONED").mean()), 4),
        attempt_format_mix=A.content_id.map(CI.set_index("content_id").format).value_counts().to_dict(),
        content_format_mix=CI.format.value_counts().to_dict(), content_status_mix=CI.status.value_counts().to_dict(),
        content_difficulty_mix={int(k): int(v) for k, v in CI.difficulty.value_counts().sort_index().items()},
        score_pct=q(sc.score_pct), pass_rate=round(float(sc.passed.mean()), 4),
        prerequisite_gap_attempts=int(len(gaps)), prerequisite_gap_attempt_share=round(len(gaps) / max(1, len(A)), 4),
        pass_rate_with_prereq_gap=round(float(A[A.attempt_id.isin(gaps) & A.score_pct.notna()].passed.mean()), 4) if len(gaps) else None,
        pass_rate_without_prereq_gap=round(float(A[~A.attempt_id.isin(gaps) & A.score_pct.notna()].passed.mean()), 4),
        current_mastery_levels=last.mastery_level.value_counts().to_dict(),
        path_status=T["LearningPath"].status.value_counts().to_dict(),
        learners_with_multiple_paths=int((T["LearningPath"].groupby("learner_id").size() > 1).sum()),
        recommendations=int(len(R)), reason_codes=R.reason_code.value_counts().to_dict(),
        recommendation_status=R.status.value_counts().to_dict(), recommendation_outcomes=R.outcome.value_counts().to_dict(),
    )


def prereq_gap_attempts(T, cat):
    """Attempts started while a REQUIRED prerequisite of the item was below min_mastery (learner went off-path)."""
    A = T["Attempt"]
    rows = []
    for r in A[["attempt_id", "learner_id", "content_id", "started_at"]].itertuples(index=False):
        it = cat.items.get(r.content_id)
        if it is None:
            continue
        for s, _ in it.skills:
            for p, mm in cat.required(s, int(r.started_at)):
                rows.append((r.attempt_id, r.learner_id, p, int(r.started_at), mm))
    if not rows:
        return set()
    need = pd.DataFrame(rows, columns=["attempt_id", "learner_id", "skill_id", "t", "min_mastery"]).sort_values("t", kind="mergesort")
    tl = rules.mastery_timeline(T).sort_values(["t", "attempt_id"], kind="mergesort")
    tl["t"] = tl["t"].astype("int64"); need["t"] = need["t"].astype("int64")
    m = pd.merge_asof(need, tl[["learner_id", "skill_id", "t", "mastery_after"]], on="t", by=["learner_id", "skill_id"],
                      direction="backward", allow_exact_matches=False)
    m["mastery_after"] = m["mastery_after"].fillna(0.0)
    return set(m[m.mastery_after < m.min_mastery - 1e-9].attempt_id)


def all_metrics(T, gt, cat, true_mastery, max_eval_learners=3000):
    return dict(detection=detection_metrics(T, gt, cat), recommendation_quality=temporal_evaluation(T, cat, max_eval_learners),
                mastery_quality=mastery_vs_truth(T, true_mastery), outcomes_by_reason_code=outcomes_by_reason(T),
                distributions=distribution_metrics(T, cat))
