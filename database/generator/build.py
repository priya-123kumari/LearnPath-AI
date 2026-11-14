"""Orchestrates the whole pipeline. Deterministic: one seeded RNG, no wall-clock, stable ordering."""
import random
import numpy as np
import pandas as pd
from backend.engine import Catalog
from .config import Config
from .master_data import build_master
from .simulate import build_learners, simulate
from .derive import rec_outcomes, derive_paths
from . import anomalies as X, ids
from .schema import SCHEMA, GROUND_TRUTH_COLUMNS, columns


def _df(name, rows):
    return pd.DataFrame(rows, columns=columns(name))


def catalog_of(T):
    return Catalog.from_tables(T)


def generate_all(cfg: Config | None = None):
    cfg = cfg or Config()
    rng = np.random.default_rng(cfg.seed)
    py = random.Random(int(rng.integers(2 ** 62)))
    gt = []

    # 1. master data first (skill graph, content, N:M content-skill bridge)
    M = build_master(rng, cfg)
    for i, r in enumerate(M["content_skills"]):
        r["content_skill_id"] = ids.content_skill(i + 1)
    T = dict(Course=_df("Course", M["courses"]), Skill=_df("Skill", M["skills"]), SkillPrerequisite=_df("SkillPrerequisite", M["prereqs"]),
             ContentItem=_df("ContentItem", M["content"]), ContentSkill=_df("ContentSkill", M["content_skills"]))
    cat = catalog_of(T)
    # 2. learners and their event history (valid parent IDs by construction); the backend engine makes every recommendation
    learners, traits = build_learners(rng, cfg)
    S = simulate(rng, cfg, cat, M, learners, traits)
    attempts, results, recs, events, paths = S["attempts"], S["results"], S["recs"], S["events"], S["paths"]
    for i, r in enumerate(results):
        r["result_id"] = ids.result(i + 1)
    by_id = {a["attempt_id"]: a for a in attempts}
    by_learner = {}
    for a in attempts:
        by_learner.setdefault(a["learner_id"], []).append(a)

    # 3. labelled edge cases on top of the valid baseline (disjoint targets)
    X.inject_timestamp_invalid(py, cfg, cat, attempts, recs, paths, learners, gt)
    X.inject_future_mastery(py, cfg, results, by_id, gt, exclude_attempts=set())
    X.inject_missing_skill(py, cfg, cat, M["content_skills"], len(M["skills"]), gt)
    X.inject_prereq_violation(py, cfg, cat, recs, by_learner, gt)
    touched = {g["entity_id"][4:14] for g in gt if g["entity_type"] == "ATTEMPT"}
    fut = {g["entity_id"] for g in gt if g["entity_type"] == "ASSESSMENT_RESULT"}
    touched |= {r["learner_id"] for r in results if r["result_id"] in fut}
    rec_by_tmp = {r["rec_tmp"]: r for r in recs}
    touched |= {rec_by_tmp[g["entity_id"][1]]["learner_id"] for g in gt if g["entity_type"] == "RECOMMENDATION"}
    completed = {pid: "COMPLETED" for s in S["states"].values() for pid, ps in s["paths"].items() if ps["completed_at"] is not None}
    rec_counter = [max(rec_by_tmp)]
    X.inject_path_loops(py, cfg, cat, recs, events, paths, completed, learners, by_learner, rec_counter, gt, touched)

    # 4. derived values from the final source records
    for r in recs:
        r["_key"] = r["rec_tmp"]
    outc = rec_outcomes(recs, attempts)
    for r in recs:
        r.update(outc[r["rec_tmp"]])
    skills_per_course = {c["course_id"]: 0 for c in M["courses"]}
    for s in M["skills"]:
        skills_per_course[s["course_id"]] += 1
    status_events, summary = derive_paths(paths, events, attempts, learners, skills_per_course)
    for p in paths:
        p.update(summary[p["path_id"]])

    # 5. final immutable IDs (chronological REC ids; PEV ids/seq in path order) and FK remapping
    recs.sort(key=lambda r: (r["recommended_at"], r["learner_id"], r["rank"], r["rec_tmp"]))
    rid = {}
    for i, r in enumerate(recs):
        rid[r["rec_tmp"]] = r["recommendation_id"] = ids.recommendation(i + 1)
        r["model_version"] = "LP-RULES-1.0"
    for a in attempts:
        a["recommendation_id"] = rid.get(a["rec_tmp"])
    all_ev = events + status_events
    for e in all_ev:
        e["recommendation_id"] = rid.get(e["rec_tmp"])
    all_ev.sort(key=lambda e: (e["path_id"], e["event_at"], e["order"], e["skill_id"] or "", e["recommendation_id"] or "", e["to_status"] or ""))
    seq = {}
    for i, e in enumerate(all_ev):
        e["event_id"] = ids.path_event(i + 1)
        seq[e["path_id"]] = seq.get(e["path_id"], 0) + 1
        e["event_seq"] = seq[e["path_id"]]
    cs = sorted(M["content_skills"], key=lambda r: (r["content_id"], -r["is_primary"], r["skill_id"]))
    for i, r in enumerate(cs):
        r["content_skill_id"] = ids.content_skill(i + 1)
        if "_gt" in r:
            gt[r["_gt"]]["entity_id"] = r["content_skill_id"]
    for g in gt:
        if isinstance(g["entity_id"], tuple):
            g["entity_id"] = rid[g["entity_id"][1]]
    gt.sort(key=lambda g: (g["issue_type"], g["entity_id"]))
    for i, g in enumerate(gt):
        g["gt_id"] = ids.gt(i + 1)

    T.update(ContentSkill=_df("ContentSkill", cs), Learner=_df("Learner", learners), LearningPath=_df("LearningPath", paths),
             LearningPathEvent=_df("LearningPathEvent", all_ev), Attempt=_df("Attempt", attempts),
             AssessmentResult=_df("AssessmentResult", results), Recommendation=_df("Recommendation", recs))
    for name, spec in SCHEMA.items():
        T[name] = T[name][columns(name)].sort_values(spec["pk"], kind="mergesort").reset_index(drop=True)
    ground_truth = pd.DataFrame(gt, columns=GROUND_TRUTH_COLUMNS).sort_values("gt_id").reset_index(drop=True)
    true_mastery = pd.DataFrame(S["true_mastery"]).sort_values(["learner_id", "skill_id"]).reset_index(drop=True)
    return dict(tables=T, ground_truth=ground_truth, true_mastery=true_mastery, config=cfg, catalog=cat)
