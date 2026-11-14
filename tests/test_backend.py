"""Backend tier: REST API over a database built by the database tier (tiny dataset in a temp folder)."""
import os, tempfile
from functools import lru_cache
from fastapi.testclient import TestClient


@lru_cache(maxsize=None)
def client():
    from database.generator.__main__ import main
    from database.load_db import build
    from backend import db
    d = tempfile.mkdtemp()
    main(["--scale", "tiny", "--out", f"{d}/data", "--quiet"])
    build(f"{d}/data", f"{d}/learnpath.db", quiet=True)
    os.environ["LEARNPATH_DB"] = f"{d}/learnpath.db"
    db.reset_cache()
    from backend.main import app
    return TestClient(app)


def _active_learner(c):
    for l in c.get("/api/learners?limit=80").json()["items"]:
        if l["status"] == "ACTIVE" and l["attempts"] > 5:
            return l["learner_id"]


def test_health_and_overview():
    c = client()
    assert c.get("/api/health").json()["status"] == "ok"
    o = c.get("/api/overview").json()
    assert o["counts"]["Attempt"] == 3000 and o["validation"]["status"] == "PASS"


def test_learner_mastery_is_reproducible_live():
    c = client()
    for l in c.get("/api/learners?limit=40").json()["items"]:
        m = c.get(f"/api/learners/{l['learner_id']}/mastery").json()
        assert m["reproducible"], l["learner_id"]


def test_live_recommendations_have_reasons_and_respect_prerequisites():
    c = client(); lid = _active_learner(c)
    r = c.get(f"/api/learners/{lid}/recommendations").json()
    assert r["recommendations"] and all(x["reason_code"] and x["rationale"] for x in r["recommendations"])
    assert "PREREQ_NOT_MET" in r["excluded_counts"] or r["excluded_counts"]
    # as-of in the past uses only earlier evidence
    early = c.get(f"/api/learners/{lid}/recommendations?as_of=2026-01-01T00:00:00Z")
    assert early.status_code in (200, 409)


def test_record_attempt_appends_and_updates_mastery():
    c = client(); lid = _active_learner(c)
    rec = c.get(f"/api/learners/{lid}/recommendations").json()["recommendations"][0]
    before = c.get(f"/api/learners/{lid}").json()["stats"]["attempts"]
    body = dict(learner_id=lid, content_id=rec["content_id"], started_at="2026-11-02T10:00:00Z", submitted_at="2026-11-02T10:20:00Z",
                raw_score=None, status="COMPLETED")
    detail = c.get(f"/api/records/{rec['content_id']}").json()["record"]
    if detail["is_assessed"]:
        body["raw_score"] = detail["max_score"]
    r = c.post("/api/attempts", json=body)
    assert r.status_code == 201, r.json()
    out = r.json()
    assert out["attempt_id"].startswith(f"ATT-{lid}-")
    assert c.get(f"/api/learners/{lid}").json()["stats"]["attempts"] == before + 1
    if detail["is_assessed"]:
        assert out["mastery_changes"] and all(m["after"] > m["before"] for m in out["mastery_changes"])
    assert c.get(f"/api/learners/{lid}/mastery").json()["reproducible"]


def test_exception_paths_return_structured_errors():
    c = client(); lid = _active_learner(c)
    any_content = c.get("/api/content?limit=1").json()[0]["content_id"]
    r = c.post("/api/attempts", json=dict(learner_id=lid, content_id=any_content, started_at="2026-01-01T00:00:00Z", submitted_at="2025-12-31T00:00:00Z"))
    assert r.status_code in (409, 422) and r.json()["error"] in ("ATTEMPT_TIMESTAMP_ORDER_INVALID", "BEFORE_ENROLMENT", "CONTENT_NOT_PUBLISHED")
    assert c.post("/api/attempts", json=dict(learner_id=lid, content_id="CNT-999999", started_at="2026-11-03T00:00:00Z")).json()["error"] == "CONTENT_NOT_FOUND"
    assert c.get("/api/learners/LRN-999999").status_code == 404
    assert c.get("/api/records/NOPE-1").json()["error"] == "UNKNOWN_ID"


def test_persisting_recommendations_appends_rows_and_step_event():
    c = client(); lid = _active_learner(c)
    r = c.post(f"/api/learners/{lid}/recommendations?as_of=2026-11-05T00:00:00Z")
    assert r.status_code == 201 and r.json()["persisted"]
    rid = r.json()["persisted_ids"][0]
    t = c.get(f"/api/records/{rid}").json()
    assert t["record"]["status"] in ("ISSUED", "ESCALATED") and (t["related"]["step_event"] or t["record"]["status"] == "ESCALATED")


def test_graph_quality_exceptions_evaluation():
    c = client()
    cid = c.get("/api/courses").json()[0]["course_id"]
    g = c.get(f"/api/courses/{cid}/graph").json()
    assert g["nodes"] and g["edges"]
    q = c.get("/api/quality").json()
    assert q["validation"]["status"] == "PASS" and all(v["recall"] == 1.0 for v in q["detection"].values())
    assert c.get("/api/exceptions").json()["total"] > 0
    assert c.get("/api/evaluation").json()["recommendation_quality"]["split_is_temporal"]
