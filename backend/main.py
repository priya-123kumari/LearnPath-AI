"""Backend tier: REST API over the LearnPath database.

    python -m uvicorn backend.main:app --reload --port 8000   (run from the repo root; docs at http://localhost:8000/docs)

The frontend tier calls only these endpoints; nothing outside backend/ touches the database at runtime.
"""
from typing import Optional
from fastapi import FastAPI, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from . import service as S
from . import db
from .config import MODEL_VERSION, MASTERY_MODEL, iso, AS_OF

app = FastAPI(title="LearnPath AI API", version="1.0.0",
              description="Next-activity recommendations from skills, prerequisites, assessment results and content difficulty.")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:4173"],
                   allow_methods=["*"], allow_headers=["*"])


@app.exception_handler(S.ApiError)
def api_error(_: Request, e: S.ApiError):
    return JSONResponse(status_code=e.status, content=dict(error=e.code, message=e.message, detail=e.detail))


@app.exception_handler(FileNotFoundError)
def no_db(_: Request, e: FileNotFoundError):
    return JSONResponse(status_code=503, content=dict(error="DATABASE_NOT_READY", message=str(e)))


class AttemptIn(BaseModel):
    learner_id: str = Field(examples=["LRN-000001"])
    content_id: str = Field(examples=["CNT-000001"])
    started_at: str = Field(examples=["2026-11-01T09:00:00Z"])
    submitted_at: Optional[str] = Field(default=None, examples=["2026-11-01T09:12:00Z"])
    status: str = "COMPLETED"
    raw_score: Optional[int] = None
    recommendation_id: Optional[str] = None
    duration_sec: Optional[int] = None
    completion_pct: Optional[float] = None


@app.get("/api/health")
def health():
    ok = True
    try:
        db.scalar("SELECT 1")
    except FileNotFoundError:
        ok = False
    return dict(status="ok" if ok else "database_missing", database=db.db_path(), model_version=MODEL_VERSION,
                mastery_model=MASTERY_MODEL, dataset_as_of=iso(AS_OF))


@app.get("/api/overview")
def overview():
    return S.overview()


@app.get("/api/learners")
def learners(q: str = "", status: Optional[str] = None, limit: int = Query(50, ge=1, le=500), offset: int = Query(0, ge=0)):
    return S.list_learners(q, status, limit, offset)


@app.get("/api/learners/{learner_id}")
def learner(learner_id: str):
    return S.learner_detail(learner_id)


@app.get("/api/learners/{learner_id}/mastery")
def learner_mastery(learner_id: str, as_of: Optional[str] = None):
    return S.mastery(learner_id, as_of)


@app.get("/api/learners/{learner_id}/recommendations")
def learner_recommend(learner_id: str, as_of: Optional[str] = None, k: int = 3):
    """Live engine run (read-only): ranked items, reason codes, rationale and why other items were excluded."""
    return S.recommend_live(learner_id, as_of, k, persist=False)


@app.post("/api/learners/{learner_id}/recommendations", status_code=201)
def learner_recommend_persist(learner_id: str, as_of: Optional[str] = None, k: int = 3):
    """Run the engine and append the recommendations (+ STEP_ASSIGNED path event) to the database."""
    return S.recommend_live(learner_id, as_of, k, persist=True)


@app.post("/api/attempts", status_code=201)
def post_attempt(a: AttemptIn):
    return S.record_attempt(a.model_dump())


@app.get("/api/courses")
def courses():
    return S.courses()


@app.get("/api/courses/{course_id}/graph")
def course_graph(course_id: str, learner_id: Optional[str] = None, as_of: Optional[str] = None):
    return S.course_graph(course_id, learner_id, as_of)


@app.get("/api/content")
def content(course_id: Optional[str] = None, skill_id: Optional[str] = None, format: Optional[str] = None, limit: int = Query(100, ge=1, le=1000)):
    return S.content_list(course_id, skill_id, format, limit)


@app.get("/api/records/{record_id}")
def record(record_id: str):
    return S.trace(record_id)


@app.get("/api/quality")
def quality():
    return S.quality()


@app.get("/api/exceptions")
def exceptions(exception_type: Optional[str] = None, owner_role: Optional[str] = None, limit: int = Query(100, ge=1, le=1000), offset: int = Query(0, ge=0)):
    return S.exceptions(exception_type, owner_role, limit, offset)


@app.get("/api/evaluation")
def evaluation():
    return S.evaluation()
