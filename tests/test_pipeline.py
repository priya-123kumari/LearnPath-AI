"""Database tier: generator, derived values, validation, anomalies, reproducibility and SQL export."""
import json, os, sqlite3, tempfile
import pandas as pd
import pytest
from helpers import dataset, clone_tables
from backend.engine import replay
from database.generator.__main__ import main
from database.generator.build import generate_all
from database.generator.config import Config, SCALES, TEMPORAL_CUTOFF
from database.generator.evaluate import detection_metrics, temporal_evaluation, prereq_gap_attempts
from database.generator.export import ddl, seed_sql, _prep
from database.generator.ids import ID_PATTERNS
from database.generator.schema import SCHEMA, LEAK_COLUMNS, ISSUE_TYPES
from database.generator.validate import validate
from database.generator import rules


# ---------- IDs and volumes ----------
def test_id_formats_match_spec():
    T = dataset()["tables"]
    for key, pat in ID_PATTERNS.items():
        t, c = key.split(".")
        assert T[t][c].astype(str).str.match(pat).all(), key
    assert T["Learner"].learner_id.iloc[0] == "LRN-000001" and T["Course"].course_id.iloc[0] == "CRS-000001"
    assert T["LearningPath"].path_id.iloc[0] == "PATH-2026-000001"
    a = T["Attempt"]
    assert (a.attempt_id.str[4:14] == a.learner_id).all()
    assert a[a.learner_id == a.learner_id.iloc[0]].attempt_id.iloc[0].endswith("-000001")


def test_exact_volumes_and_scale_parameter():
    R = dataset(); T, cfg = R["tables"], R["config"]
    assert len(T["Learner"]) == cfg.learners and len(T["Skill"]) == cfg.skills
    assert len(T["ContentItem"]) == cfg.content and len(T["Attempt"]) == cfg.attempts
    with pytest.raises(ValueError):
        Config(skills=35)


# ---------- reproducibility ----------
def test_same_seed_identical_and_different_seed_differs():
    a = generate_all(Config(**SCALES["tiny"])); b = generate_all(Config(**SCALES["tiny"]))
    for k in a["tables"]:
        pd.testing.assert_frame_equal(a["tables"][k], b["tables"][k])
    pd.testing.assert_frame_equal(a["ground_truth"], b["ground_truth"])
    c = generate_all(Config(seed=1, **SCALES["tiny"]))
    assert not a["tables"]["Attempt"].score_pct.equals(c["tables"]["Attempt"].score_pct)


def test_cli_checksums_identical_across_runs():
    with tempfile.TemporaryDirectory() as d:
        main(["--scale", "tiny", "--out", f"{d}/a", "--quiet"]); main(["--scale", "tiny", "--out", f"{d}/b", "--quiet"])
        ca = json.load(open(f"{d}/a/checksums.json")); cb = json.load(open(f"{d}/b/checksums.json"))
        assert ca == cb and len(ca) >= 30


# ---------- validation ----------
def test_validation_passes_on_generated_data():
    R = dataset()
    v = validate(R["tables"], R["ground_truth"], R["catalog"])
    assert v["status"] == "PASS", v["unexpected_error_samples"]
    assert v["unexpected_errors"] == 0 and v["missed_labelled"] == 0 and v["checks_run"] > 200


def _broken(mutate):
    R = dataset(); T = clone_tables(R)
    mutate(T)
    return validate(T, R["ground_truth"], R["catalog"])


def test_validation_fails_on_deliberately_broken_rows():
    a0 = lambda T: T["Attempt"][T["Attempt"].score_pct.notna()].index[5]
    cases = {
        "fk": lambda T: T["Attempt"].__setitem__("content_id", T["Attempt"].content_id.where(T["Attempt"].index != 3, "CNT-999999")),
        "enum": lambda T: T["Recommendation"].loc.__setitem__((0, "reason_code"), "BECAUSE"),
        "duplicate_pk": lambda T: T.__setitem__("Learner", pd.concat([T["Learner"], T["Learner"].iloc[[0]]], ignore_index=True)),
        "arithmetic": lambda T: T["Attempt"].loc.__setitem__((a0(T), "score_pct"), 1.23),
        "mastery_derived": lambda T: T["AssessmentResult"].loc.__setitem__((10, "mastery_after"), 0.999),
        "rec_outcome_derived": lambda T: T["Recommendation"].loc.__setitem__((T["Recommendation"].index[T["Recommendation"].outcome == "COMPLETED_PASS"][0], "outcome"), "COMPLETED_FAIL"),
        "missing_reason": lambda T: T["Recommendation"].loc.__setitem__((1, "rationale"), ""),
        "lifecycle": lambda T: T["LearningPath"].loc.__setitem__((0, "status"), "COMPLETED"),
        "dates": lambda T: T["Learner"].loc.__setitem__((0, "enrolled_at"), 0),
    }
    for name, fn in cases.items():
        v = _broken(fn)
        assert v["status"] == "FAIL" and v["unexpected_errors"] > 0, name


# ---------- anomalies & ground truth ----------
def test_every_injected_anomaly_is_detected_by_rules():
    R = dataset()
    m = detection_metrics(R["tables"], R["ground_truth"], R["catalog"])
    for typ in ISSUE_TYPES:
        assert m[typ]["ground_truth"] >= 2, typ
        assert m[typ]["precision"] == 1.0 and m[typ]["recall"] == 1.0, (typ, m[typ])


def test_anomalies_are_rare_and_disjoint():
    R = dataset(); gt = R["ground_truth"]
    assert gt.entity_id.is_unique and gt.gt_id.is_unique
    assert len(gt) / len(R["tables"]["Attempt"]) < 0.02


def test_ground_truth_not_leaked_into_inputs():
    R = dataset()
    for name, df in R["tables"].items():
        assert not (set(df.columns) & LEAK_COLUMNS), name
    assert "true_mastery" not in R["tables"]["AssessmentResult"].columns


# ---------- acceptance criteria ----------
def test_prerequisites_respected_except_labelled_cases():
    R = dataset(); T, gt = R["tables"], R["ground_truth"]
    viol = set(rules.prereq_violations(T, R["catalog"]))
    assert viol == set(gt[gt.issue_type == "RECOMMENDATION_VIOLATES_PREREQUISITE"].entity_id)


def test_mastery_calculation_is_reproducible_from_attempts():
    R = dataset(); T, cat = R["tables"], R["catalog"]
    last = T["AssessmentResult"].sort_values("evidence_count").groupby(["learner_id", "skill_id"]).tail(1)
    for lid, g in T["Attempt"].groupby("learner_id"):
        st = replay(cat, g.to_dict("records"))
        want = last[last.learner_id == lid].set_index("skill_id").mastery_after.to_dict()
        assert {s: st.mastery[s] for s in want} == want, lid


def test_temporal_split_is_used():
    R = dataset("starter" and 20261022, "starter")
    out = temporal_evaluation(R["tables"], R["catalog"], max_learners=150)
    assert out["split_is_temporal"] and out["train_max_started"] < out["test_min_started"]
    assert out["engine"]["prerequisite_violation_rate"] == 0.0 and out["engine"]["reason_code_coverage"] == 1.0
    assert out["learners_evaluated"] > 50


def test_recommendations_have_reason_codes_and_outcomes():
    T = dataset()["tables"]; r = T["Recommendation"]
    assert r.reason_code.notna().all() and (r.rationale.str.len() > 20).all()
    assert set(r.outcome) <= {"PENDING", "NOT_ATTEMPTED", "COMPLETED_PASS", "COMPLETED_FAIL", "COMPLETED_UNSCORED", "ABANDONED", "ESCALATED"}
    assert (r.status == "ACCEPTED").mean() > 0.5


def test_coverage_cold_start_repeats_gaps_and_formats():
    R = dataset("starter" and 20261022, "starter"); T = R["tables"]
    per = T["Attempt"].groupby("learner_id").size().reindex(T["Learner"].learner_id, fill_value=0)
    assert (per == 0).sum() > 0                                       # cold-start learners
    assert (T["Attempt"].attempt_no > 1).mean() > 0.2                 # repeated attempts
    assert len(prereq_gap_attempts(T, R["catalog"])) > 0              # prerequisite gaps
    assert T["ContentItem"].format.nunique() == 6                     # multiple content formats
    assert (T["Learner"].status == "WITHDRAWN").any() and (T["LearningPath"].status == "STALLED").any()


def test_history_is_append_only_and_paths_derived_from_events():
    T = dataset()["tables"]; ev = T["LearningPathEvent"]
    last = ev[ev.to_status.notna()].sort_values(["path_id", "event_seq"]).groupby("path_id").to_status.last()
    assert (T["LearningPath"].set_index("path_id").status == last).all()
    created = ev[ev.event_type == "PATH_CREATED"]
    assert created.path_id.is_unique and len(created) == len(T["LearningPath"])


# ---------- SQL export ----------
def test_sql_seed_loads_into_sqlite_and_fk_check_lists_only_labelled_rows():
    R = dataset(); P = {n: _prep(n, R["tables"][n]) for n in SCHEMA}
    con = sqlite3.connect(":memory:")
    con.executescript(ddl()); con.executescript(seed_sql(P))
    for n, spec in SCHEMA.items():
        assert con.execute(f"SELECT COUNT(*) FROM {spec['file']}").fetchone()[0] == len(R["tables"][n])
    bad = con.execute("PRAGMA foreign_key_check").fetchall()
    rowid = dict(con.execute("SELECT rowid, content_skill_id FROM content_skills").fetchall())
    gt = R["ground_truth"]
    assert sorted(rowid[r[1]] for r in bad) == sorted(gt[gt.issue_type == "CONTENT_MAPPED_TO_NONEXISTENT_SKILL"].entity_id)
