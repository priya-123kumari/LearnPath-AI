"""Application services of the backend tier: learner state, live recommendations, recording attempts, tracing records.

All writes are appends (new attempt, evidence, recommendation and path-event rows). Only DERIVED summary fields
(recommendation outcome, path status/progress) are refreshed, by the same documented rules the generator uses.
"""
from .config import (AS_OF, DAY, MASTERED_AT, OUTCOME_WINDOW_DAYS, STALL_AFTER_DAYS, REASON_CODES, EXCLUSION_CODES,
                     MODEL_VERSION, MASTERY_MODEL, PASS_PCT, iso, parse_iso)
from .engine import replay, recommend, mastery_level
from . import db

TABLES = [("learners", "Learner"), ("courses", "Course"), ("skills", "Skill"), ("skill_prerequisites", "SkillPrerequisite"),
          ("content_items", "ContentItem"), ("content_skills", "ContentSkill"), ("learning_paths", "LearningPath"),
          ("learning_path_events", "LearningPathEvent"), ("attempts", "Attempt"), ("assessment_results", "AssessmentResult"),
          ("recommendations", "Recommendation")]
PREFIX = {"LRN": ("learners", "learner_id"), "CRS": ("courses", "course_id"), "SKL": ("skills", "skill_id"),
          "CNT": ("content_items", "content_id"), "SPR": ("skill_prerequisites", "prerequisite_id"),
          "CSK": ("content_skills", "content_skill_id"), "ATT": ("attempts", "attempt_id"), "PATH": ("learning_paths", "path_id"),
          "ASR": ("assessment_results", "result_id"), "PEV": ("learning_path_events", "event_id"), "REC": ("recommendations", "recommendation_id")}


class ApiError(Exception):
    def __init__(self, status, code, message, detail=None):
        super().__init__(message)
        self.status, self.code, self.message, self.detail = status, code, message, detail


def _as_of(v):
    if v in (None, ""):
        return AS_OF
    try:
        return parse_iso(v)
    except ValueError:
        raise ApiError(422, "INVALID_TIMESTAMP", f"as_of must be ISO-8601 like 2026-09-01T00:00:00Z, got {v!r}")


def learner_or_404(lid):
    L = db.one("SELECT * FROM learners WHERE learner_id = ?", (lid,))
    if not L:
        raise ApiError(404, "LEARNER_NOT_FOUND", f"No learner {lid}")
    return L


def _attempts(lid):
    return db.rows("SELECT * FROM attempts WHERE learner_id = ? ORDER BY attempt_id", (lid,))


def build_state(lid, t):
    cat = db.catalog()
    st = replay(cat, _attempts(lid), as_of=t)
    for r in db.rows("""SELECT e.path_id, e.content_id, e.mastery_snapshot FROM learning_path_events e JOIN learning_paths p ON p.path_id = e.path_id
                        WHERE p.learner_id = ? AND e.event_type = 'STEP_ASSIGNED' AND e.event_at <= ? ORDER BY e.path_id, e.event_seq""", (lid, iso(t))):
        st.steps.setdefault(r["path_id"], {}).setdefault(r["content_id"], []).append(float(r["mastery_snapshot"] or 0))
    return cat, st


def open_paths(lid, t, L=None):
    L = L or learner_or_404(lid)
    if L["withdrawn_at"] and parse_iso(L["withdrawn_at"]) <= t:
        return []
    ps = db.rows("SELECT path_id, course_id, created_at, completed_at FROM learning_paths WHERE learner_id = ? ORDER BY created_at, path_id", (lid,))
    return [(p["path_id"], p["course_id"]) for p in ps
            if parse_iso(p["created_at"]) <= t and not (p["completed_at"] and parse_iso(p["completed_at"]) <= t)]


# ------------------------------------------------------------------ read models
def overview():
    counts = {label: db.scalar(f"SELECT COUNT(*) FROM {t}") for t, label in TABLES}
    val, met, man = db.report("validation_summary"), db.report("evaluation_metrics"), db.report("source_manifest")
    d = met["distributions"]
    exc = db.rows("SELECT exception_type, owner_role, COUNT(*) AS n FROM audit_exception_queue GROUP BY exception_type, owner_role ORDER BY n DESC")
    return dict(counts=counts, dataset=db.report("dataset"), seed=man["seed"], scale=man["scale"], generator_command=man["generator_command"],
                validation=dict(status=val["status"], checks_run=val["checks_run"], total_rows_checked=val["total_rows_checked"],
                                unexpected_errors=val["unexpected_errors"], labelled_findings_observed=val["labelled_findings_observed"],
                                missed_labelled=val["missed_labelled"]),
                recommendation_quality=met["recommendation_quality"], mastery_quality=met["mastery_quality"], distributions=d,
                exceptions=exc, as_of=iso(AS_OF), timeline=timeline())


def timeline():
    """Weekly activity (Monday-start weeks): attempts, active learners, pass rate and recommendations issued."""
    att = db.rows("""SELECT date(substr(started_at, 1, 10), '-6 days', 'weekday 1') AS week, COUNT(*) AS attempts,
                     COUNT(DISTINCT learner_id) AS active_learners, AVG(passed) AS pass_rate
                     FROM attempts GROUP BY week ORDER BY week""")
    recs = {r["week"]: r["n"] for r in db.rows("""SELECT date(substr(recommended_at, 1, 10), '-6 days', 'weekday 1') AS week, COUNT(*) AS n
                                                  FROM recommendations GROUP BY week""")}
    for r in att:
        r["recommendations"] = recs.get(r["week"], 0)
        r["pass_rate"] = round(r["pass_rate"], 4) if r["pass_rate"] is not None else None
    return att


def list_learners(q="", status=None, limit=50, offset=0):
    where, params = [], []
    if q:
        where.append("(l.learner_id LIKE ? OR l.display_name LIKE ? OR l.email LIKE ?)"); params += [f"%{q}%"] * 3
    if status:
        where.append("l.status = ?"); params.append(status)
    w = ("WHERE " + " AND ".join(where)) if where else ""
    total = db.scalar(f"SELECT COUNT(*) FROM learners l {w}", params)
    items = db.rows(f"""SELECT l.learner_id, l.display_name, l.country, l.prior_level, l.cohort, l.status, l.enrolled_at,
                          (SELECT COUNT(*) FROM attempts a WHERE a.learner_id = l.learner_id) AS attempts,
                          (SELECT COUNT(*) FROM learning_paths p WHERE p.learner_id = l.learner_id) AS paths
                        FROM learners l {w} ORDER BY l.learner_id LIMIT ? OFFSET ?""", params + [limit, offset])
    return dict(total=total, items=items, limit=limit, offset=offset)


def learner_detail(lid):
    L = learner_or_404(lid)
    paths = db.rows("""SELECT p.*, c.title AS course_title, c.course_code FROM learning_paths p JOIN courses c ON c.course_id = p.course_id
                       WHERE p.learner_id = ? ORDER BY p.created_at""", (lid,))
    att = db.rows("""SELECT a.*, c.title AS content_title, c.format FROM attempts a JOIN content_items c ON c.content_id = a.content_id
                     WHERE a.learner_id = ? ORDER BY a.attempt_id DESC LIMIT 100""", (lid,))
    recs = db.rows("""SELECT r.*, c.title AS content_title, c.format, c.difficulty FROM recommendations r LEFT JOIN content_items c ON c.content_id = r.content_id
                      WHERE r.learner_id = ? ORDER BY r.recommended_at DESC, r.rank LIMIT 90""", (lid,))
    stats = db.one("""SELECT COUNT(*) AS attempts, SUM(status='COMPLETED') AS completed, AVG(score_pct) AS avg_score, AVG(passed) AS pass_rate,
                      MIN(started_at) AS first_attempt, MAX(started_at) AS last_attempt FROM attempts WHERE learner_id = ?""", (lid,))
    return dict(learner=L, stats=stats, paths=paths, recent_attempts=att, recommendations=recs,
                mastery=mastery(lid)["skills"], cold_start=stats["attempts"] == 0)


def mastery(lid, as_of=None):
    """Mastery replayed live from attempts (reproducible), compared with the latest stored evidence row."""
    learner_or_404(lid)
    t = _as_of(as_of)
    cat, st = build_state(lid, t)
    stored = {r["skill_id"]: r for r in db.rows("""SELECT r.skill_id, r.mastery_after, r.evidence_count FROM assessment_results r
        JOIN attempts a ON a.attempt_id = r.attempt_id WHERE r.learner_id = ? AND a.submitted_at <= ?
        ORDER BY a.submitted_at, r.attempt_id""", (lid, iso(t)))}
    out = []
    for sid in sorted(set(st.mastery) | set(stored)):
        sk = cat.skills.get(sid, {})
        m, n = st.mastery.get(sid, 0.0), st.evidence.get(sid, 0)
        s = stored.get(sid)
        out.append(dict(skill_id=sid, skill_name=sk.get("name"), course_id=sk.get("course_id"), tier=sk.get("tier"), mastery=m, evidence_count=n,
                        mastery_level=mastery_level(m, n), last_practiced_at=iso(st.last_practiced.get(sid)),
                        stored_mastery=s["mastery_after"] if s else None, matches_stored=bool(s) and abs(s["mastery_after"] - m) < 1e-9))
    return dict(learner_id=lid, as_of=iso(t), model=MASTERY_MODEL, skills=out,
                reproducible=all(x["matches_stored"] for x in out))


def recommend_live(lid, as_of=None, k=3, persist=False):
    L = learner_or_404(lid)
    t = _as_of(as_of)
    if not 1 <= k <= 10:
        raise ApiError(422, "INVALID_K", "k must be between 1 and 10")
    cat, st = build_state(lid, t)
    paths = open_paths(lid, t, L)
    if not paths:
        raise ApiError(409, "NO_OPEN_PATH", f"{lid} has no open learning path at {iso(t)} (withdrawn, completed or not yet enrolled)")
    res = recommend(cat, st, paths, t, k=k, explain=True)
    for r in res["recs"]:
        it = cat.items.get(r["content_id"]) if r["content_id"] else None
        r.update(content_title=it.title if it else None, format=it.format if it else None, difficulty=it.difficulty if it else None,
                 course_id=it.course_id if it else None, skill_name=cat.skills[r["skill_id"]]["name"] if r["skill_id"] else None,
                 reason_text=REASON_CODES[r["reason_code"]])
    groups = {c: [] for c in EXCLUSION_CODES}
    for e in res["exclusions"]:
        groups[e["code"]].append(e)
    out = dict(learner_id=lid, as_of=iso(t), model_version=MODEL_VERSION, open_paths=[dict(path_id=p, course_id=c) for p, c in paths],
               evidence_rows=st.total_evidence, cold_start=st.total_evidence == 0, escalated=res["escalated"],
               recommendations=res["recs"], excluded_counts=res["excluded"],
               exclusions_sample={c: v[:8] for c, v in groups.items() if v}, persisted=False)
    if persist:
        out["persisted_ids"] = _persist_recs(lid, res["recs"], t)
        out["persisted"] = True
    return out


def _next(table, col, prefix, width):
    m = db.scalar(f"SELECT MAX({col}) FROM {table}")
    n = int(m.rsplit("-", 1)[1]) + 1 if m else 1
    return n, lambda i: f"{prefix}{i:0{width}d}"


def _persist_recs(lid, recs, t):
    c = db.conn()
    n, rid = _next("recommendations", "recommendation_id", "REC-", 8)
    e, eid = _next("learning_path_events", "event_id", "PEV-", 8)
    ids = []
    with c:
        for r in recs:
            new = rid(n); n += 1; ids.append(new)
            esc = r["content_id"] is None
            c.execute("""INSERT INTO recommendations (recommendation_id, learner_id, path_id, content_id, skill_id, recommended_at, rank, score,
                         reason_code, rationale, mastery_snapshot, target_difficulty, prereqs_checked, model_version, status, outcome)
                         VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                      (new, lid, r["path_id"], r["content_id"], r["skill_id"], iso(t), r["rank"], r["score"], r["reason_code"], r["rationale"],
                       r["mastery_snapshot"], r["target_difficulty"], r["prereqs_checked"], MODEL_VERSION,
                       "ESCALATED" if esc else "ISSUED", "ESCALATED" if esc else "PENDING"))
            if r["rank"] == 1 and not esc:
                seq = (db.scalar("SELECT MAX(event_seq) FROM learning_path_events WHERE path_id = ?", (r["path_id"],)) or 0) + 1
                c.execute("""INSERT INTO learning_path_events (event_id, path_id, event_seq, event_type, event_at, content_id, skill_id,
                             recommendation_id, mastery_snapshot) VALUES (?,?,?,?,?,?,?,?,?)""",
                          (eid(e), r["path_id"], seq, "STEP_ASSIGNED", iso(t), r["content_id"], r["skill_id"], new, r["mastery_snapshot"]))
                e += 1
    return ids


# ------------------------------------------------------------------ write path: record an attempt
def record_attempt(body):
    """Validate and append one attempt, its mastery evidence and any path events. Returns the mastery change."""
    lid, cid = body["learner_id"], body["content_id"]
    L = learner_or_404(lid)
    cat = db.catalog()
    it = cat.items.get(cid)
    if it is None:
        raise ApiError(404, "CONTENT_NOT_FOUND", f"No content item {cid} (or it has no valid skill mapping)")
    started = _as_of(body.get("started_at"))
    status = body.get("status", "COMPLETED")
    if status not in ("COMPLETED", "ABANDONED"):
        raise ApiError(422, "INVALID_STATUS", "status must be COMPLETED or ABANDONED")
    if L["status"] == "WITHDRAWN" and started >= parse_iso(L["withdrawn_at"]):
        raise ApiError(409, "LEARNER_WITHDRAWN", f"{lid} withdrew on {L['withdrawn_at']}")
    if started < parse_iso(L["enrolled_at"]):
        raise ApiError(422, "BEFORE_ENROLMENT", "started_at is before the learner enrolled")
    if not cat.available(it, started):
        raise ApiError(409, "CONTENT_NOT_PUBLISHED", f"{cid} is {it.status} at {iso(started)}")
    last = db.one("SELECT attempt_id, started_at FROM attempts WHERE learner_id = ? ORDER BY attempt_id DESC LIMIT 1", (lid,))
    if last and started < parse_iso(last["started_at"]):
        raise ApiError(409, "ATTEMPT_TIMESTAMP_ORDER_INVALID",
                       f"started_at {iso(started)} is earlier than the learner's previous attempt {last['attempt_id']} ({last['started_at']})")
    submitted = _as_of(body.get("submitted_at")) if status == "COMPLETED" else None
    if status == "COMPLETED" and (body.get("submitted_at") in (None, "") or submitted < started):
        raise ApiError(409, "ATTEMPT_TIMESTAMP_ORDER_INVALID", "submitted_at is required and must be >= started_at")
    raw = body.get("raw_score")
    if status == "COMPLETED" and it.assessed:
        if raw is None or not 0 <= int(raw) <= it.max_score:
            raise ApiError(422, "INVALID_SCORE", f"raw_score must be an integer 0..{it.max_score} for this {it.format}")
        raw = int(raw)
        score_pct = round(100.0 * raw / it.max_score, 2)
        passed = int(score_pct >= PASS_PCT)
    else:
        raw, score_pct, passed = None, None, None
    duration = (submitted - started) if submitted is not None else int(body.get("duration_sec") or 60)
    # path: the learner's path for this course, else the oldest open path
    path = db.one("SELECT * FROM learning_paths WHERE learner_id = ? AND course_id = ?", (lid, it.course_id))
    if path is None:
        op = open_paths(lid, started, L)
        if not op:
            raise ApiError(409, "NO_OPEN_PATH", f"{lid} has no open learning path")
        path = db.one("SELECT * FROM learning_paths WHERE path_id = ?", (op[0][0],))
    rec_id = body.get("recommendation_id") or None
    if rec_id:
        rec = db.one("SELECT * FROM recommendations WHERE recommendation_id = ?", (rec_id,))
        if not rec or rec["learner_id"] != lid or rec["content_id"] != cid:
            raise ApiError(422, "RECOMMENDATION_MISMATCH", f"{rec_id} is not a recommendation of {cid} for {lid}")
    _, st = build_state(lid, started)
    gaps = cat.unmet(it, st.mastery, started)
    seq = int(last["attempt_id"].rsplit("-", 1)[1]) + 1 if last else 1
    aid = f"ATT-{lid}-{seq:06d}"
    attempt_no = (db.scalar("SELECT MAX(attempt_no) FROM attempts WHERE learner_id = ? AND content_id = ?", (lid, cid)) or 0) + 1
    t_ev = submitted if submitted is not None else started + duration
    before = dict(st.mastery)
    evidence = st.apply_attempt(cat, it, status, score_pct, bool(passed), t_ev)
    c = db.conn()
    n, resid = _next("assessment_results", "result_id", "ASR-", 8)
    e, eid = _next("learning_path_events", "event_id", "PEV-", 8)
    new_events = []
    with c:
        c.execute("""INSERT INTO attempts (attempt_id, learner_id, content_id, path_id, recommendation_id, attempt_no, started_at, submitted_at,
                     duration_sec, status, raw_score, max_score, score_pct, passed, completion_pct) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                  (aid, lid, cid, path["path_id"], rec_id, attempt_no, iso(started), iso(submitted), duration, status, raw,
                   it.max_score if score_pct is not None else None, score_pct, passed, 100.0 if status == "COMPLETED" else float(body.get("completion_pct") or 50)))
        for ev in evidence:
            c.execute("""INSERT INTO assessment_results (result_id, attempt_id, learner_id, skill_id, content_id, evidence_weight, score_pct, mastery_before,
                         mastery_after, evidence_count, mastery_level, computed_at, model_version) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                      (resid(n), aid, lid, ev["skill_id"], cid, ev["evidence_weight"], score_pct, ev["mastery_before"], ev["mastery_after"],
                       ev["evidence_count"], ev["mastery_level"], iso(submitted), MASTERY_MODEL))
            n += 1
        seqno = db.scalar("SELECT MAX(event_seq) FROM learning_path_events WHERE path_id = ?", (path["path_id"],)) or 0

        def add_event(etype, at, **kw):
            nonlocal e, seqno
            seqno += 1
            c.execute("""INSERT INTO learning_path_events (event_id, path_id, event_seq, event_type, event_at, from_status, to_status, content_id,
                         skill_id, recommendation_id, mastery_snapshot) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                      (eid(e), path["path_id"], seqno, etype, iso(at), kw.get("frm"), kw.get("to"), None, kw.get("skill"), None, kw.get("m")))
            new_events.append(dict(event_id=eid(e), event_type=etype, **kw)); e += 1
        status_now = path["status"]
        if status_now == "STALLED":
            add_event("STATUS_CHANGED", started, frm="STALLED", to="ACTIVE"); status_now = "ACTIVE"
        mastered = {r["skill_id"] for r in db.rows("SELECT skill_id FROM learning_path_events WHERE path_id = ? AND event_type = 'SKILL_MASTERED'", (path["path_id"],))}
        course_skills = set(cat.course_skills.get(path["course_id"], []))
        for ev in evidence:
            if ev["mastery_after"] >= MASTERED_AT and ev["skill_id"] in course_skills and ev["skill_id"] not in mastered:
                add_event("SKILL_MASTERED", t_ev, skill=ev["skill_id"], m=ev["mastery_after"]); mastered.add(ev["skill_id"])
        completed_at = path["completed_at"]
        if status_now == "ACTIVE" and len(mastered) == len(course_skills) and not completed_at:
            add_event("STATUS_CHANGED", t_ev, frm="ACTIVE", to="COMPLETED"); status_now, completed_at = "COMPLETED", iso(t_ev)
        changed = db.scalar("SELECT event_at FROM learning_path_events WHERE path_id = ? AND to_status IS NOT NULL ORDER BY event_seq DESC LIMIT 1", (path["path_id"],))
        c.execute("""UPDATE learning_paths SET status = ?, status_changed_at = ?, skills_mastered = ?, progress_pct = ?, last_activity_at = ?, completed_at = ?
                     WHERE path_id = ?""", (status_now, changed, len(mastered), round(100.0 * len(mastered) / path["skills_total"], 1),
                                            max(iso(started), path["last_activity_at"] or ""), completed_at, path["path_id"]))
        # derived outcome of open recommendations for this item (first attempt within 14 days)
        for r in db.rows("""SELECT recommendation_id, recommended_at FROM recommendations WHERE learner_id = ? AND content_id = ? AND outcome = 'PENDING'""", (lid, cid)):
            ra = parse_iso(r["recommended_at"])
            if ra <= started <= ra + OUTCOME_WINDOW_DAYS * DAY:
                oc = ("ABANDONED" if status == "ABANDONED" else "COMPLETED_UNSCORED" if score_pct is None else
                      "COMPLETED_PASS" if passed else "COMPLETED_FAIL")
                c.execute("""UPDATE recommendations SET status='ACCEPTED', outcome=?, outcome_attempt_id=?, outcome_score_pct=?, outcome_at=?
                             WHERE recommendation_id = ?""", (oc, aid, score_pct, iso(started), r["recommendation_id"]))
    return dict(attempt_id=aid, attempt_no=attempt_no, path_id=path["path_id"], score_pct=score_pct, passed=passed,
                prerequisite_gap=[dict(skill_id=p, min_mastery=mm, mastery=round(have, 4)) for p, mm, have in gaps],
                mastery_changes=[dict(skill_id=ev["skill_id"], skill_name=cat.skills[ev["skill_id"]]["name"], before=before.get(ev["skill_id"], 0.0),
                                      after=ev["mastery_after"], level=ev["mastery_level"]) for ev in evidence],
                path_events=new_events, path_status=status_now)


# ------------------------------------------------------------------ catalogue
def courses():
    return db.rows("""SELECT c.*, (SELECT COUNT(*) FROM skills s WHERE s.course_id = c.course_id) AS skills,
                      (SELECT COUNT(*) FROM content_items i WHERE i.course_id = c.course_id) AS content_items,
                      (SELECT COUNT(*) FROM learning_paths p WHERE p.course_id = c.course_id) AS paths
                      FROM courses c ORDER BY c.course_id""")


def course_graph(course_id, learner_id=None, as_of=None):
    if not db.one("SELECT 1 FROM courses WHERE course_id = ?", (course_id,)):
        raise ApiError(404, "COURSE_NOT_FOUND", f"No course {course_id}")
    t = _as_of(as_of)
    cat = db.catalog()
    st = build_state(learner_id, t)[1] if learner_id else None
    if learner_id:
        learner_or_404(learner_id)
    own = cat.course_skills.get(course_id, [])
    edges = db.rows("""SELECT * FROM skill_prerequisites WHERE skill_id IN (SELECT skill_id FROM skills WHERE course_id = ?) ORDER BY prerequisite_id""", (course_id,))
    ext = sorted({e["prerequisite_skill_id"] for e in edges} - set(own))
    nodes = []
    for sid in list(own) + ext:
        sk = cat.skills.get(sid)
        if not sk:
            continue
        items = [cat.items[c] for c in cat.skill_items.get(sid, [])]
        node = dict(skill_id=sid, name=sk["name"], topic=sk["topic"], tier=sk["tier"], course_id=sk["course_id"], external=sid not in own,
                    content_available=sum(1 for i in items if cat.available(i, t)), content_total=len(items))
        if st is not None:
            m, n = st.mastery.get(sid, 0.0), st.evidence.get(sid, 0)
            unmet = [(p, mm) for p, mm in cat.required(sid, t) if st.mastery.get(p, 0.0) < mm]
            node.update(mastery=m, evidence=n, state="MASTERED" if m >= MASTERED_AT else "IN_PROGRESS" if n else "LOCKED" if unmet else "UNLOCKED")
        nodes.append(node)
    for e in edges:
        e["in_force"] = parse_iso(e["effective_from"]) <= t and (not e["effective_to"] or t <= parse_iso(e["effective_to"]) + DAY - 1)
    return dict(course=db.one("SELECT * FROM courses WHERE course_id = ?", (course_id,)), nodes=nodes, edges=edges, as_of=iso(t), learner_id=learner_id)


def content_list(course_id=None, skill_id=None, fmt=None, limit=100):
    where, p = [], []
    if course_id:
        where.append("i.course_id = ?"); p.append(course_id)
    if skill_id:
        where.append("i.content_id IN (SELECT content_id FROM content_skills WHERE skill_id = ?)"); p.append(skill_id)
    if fmt:
        where.append("i.format = ?"); p.append(fmt)
    w = ("WHERE " + " AND ".join(where)) if where else ""
    return db.rows(f"""SELECT i.*, (SELECT skill_id FROM content_skills cs WHERE cs.content_id = i.content_id AND cs.is_primary = 1) AS primary_skill_id
                       FROM content_items i {w} ORDER BY i.content_id LIMIT ?""", p + [limit])


# ------------------------------------------------------------------ trace any record
def trace(rid):
    key = "PATH" if rid.startswith("PATH-") else rid[:3]
    if key not in PREFIX:
        raise ApiError(404, "UNKNOWN_ID", f"{rid} does not match any ID convention")
    table, pk = PREFIX[key]
    rec = db.one(f"SELECT * FROM {table} WHERE {pk} = ?", (rid,))
    if not rec:
        raise ApiError(404, "NOT_FOUND", f"No record {rid}")
    rel = {}
    q = db.rows
    if key == "LRN":
        rel["paths"] = q("SELECT path_id, course_id, status, progress_pct FROM learning_paths WHERE learner_id = ?", (rid,))
        rel["latest_attempts"] = q("SELECT attempt_id, content_id, started_at, status, score_pct FROM attempts WHERE learner_id = ? ORDER BY attempt_id DESC LIMIT 10", (rid,))
    elif key == "CRS":
        rel["skills"] = q("SELECT skill_id, skill_name, tier FROM skills WHERE course_id = ? ORDER BY skill_id", (rid,))
    elif key == "SKL":
        rel["prerequisites"] = q("SELECT prerequisite_id, prerequisite_skill_id, relation_type, min_mastery, effective_to FROM skill_prerequisites WHERE skill_id = ?", (rid,))
        rel["unlocks"] = q("SELECT prerequisite_id, skill_id, min_mastery FROM skill_prerequisites WHERE prerequisite_skill_id = ?", (rid,))
        rel["content"] = q("SELECT cs.content_id, i.title, i.format, i.status, cs.is_primary FROM content_skills cs JOIN content_items i ON i.content_id = cs.content_id WHERE cs.skill_id = ?", (rid,))
    elif key == "CNT":
        rel["skills"] = q("SELECT content_skill_id, skill_id, weight, is_primary FROM content_skills WHERE content_id = ?", (rid,))
        rel["usage"] = q("SELECT COUNT(*) AS attempts, AVG(score_pct) AS avg_score, AVG(passed) AS pass_rate FROM attempts WHERE content_id = ?", (rid,))
    elif key == "ATT":
        rel["evidence"] = q("SELECT result_id, skill_id, mastery_before, mastery_after, computed_at FROM assessment_results WHERE attempt_id = ?", (rid,))
        if rec["recommendation_id"]:
            rel["followed_recommendation"] = q("SELECT recommendation_id, reason_code, rank, recommended_at FROM recommendations WHERE recommendation_id = ?", (rec["recommendation_id"],))
    elif key == "PATH":
        rel["events"] = q("SELECT event_id, event_seq, event_type, event_at, from_status, to_status, content_id, skill_id, recommendation_id, mastery_snapshot FROM learning_path_events WHERE path_id = ? ORDER BY event_seq DESC LIMIT 60", (rid,))
    elif key == "REC":
        rel["step_event"] = q("SELECT event_id, event_seq, event_at FROM learning_path_events WHERE recommendation_id = ?", (rid,))
        rel["attempts_linked"] = q("SELECT attempt_id, started_at, status, score_pct FROM attempts WHERE recommendation_id = ?", (rid,))
    elif key == "ASR":
        rel["attempt"] = q("SELECT attempt_id, started_at, submitted_at, score_pct FROM attempts WHERE attempt_id = ?", (rec["attempt_id"],))
    rel["data_quality_labels"] = q("SELECT gt_id, issue_type, expected_decision, context FROM audit_ground_truth WHERE entity_id = ?", (rid,))
    rel["exceptions"] = q("SELECT exception_id, exception_type, owner_role, detail FROM audit_exception_queue WHERE entity_id = ? LIMIT 20", (rid,))
    return dict(id=rid, table=table, record=rec, related=rel)


# ------------------------------------------------------------------ admin views
def quality():
    val, met = db.report("validation_summary"), db.report("evaluation_metrics")
    gt = db.rows("SELECT * FROM audit_ground_truth ORDER BY gt_id")
    return dict(validation=val, detection=met["detection"], ground_truth=gt)


def exceptions(exception_type=None, owner_role=None, limit=100, offset=0):
    where, p = [], []
    if exception_type:
        where.append("exception_type = ?"); p.append(exception_type)
    if owner_role:
        where.append("owner_role = ?"); p.append(owner_role)
    w = ("WHERE " + " AND ".join(where)) if where else ""
    return dict(total=db.scalar(f"SELECT COUNT(*) FROM audit_exception_queue {w}", p),
                summary=db.rows("SELECT exception_type, owner_role, COUNT(*) AS n FROM audit_exception_queue GROUP BY 1, 2 ORDER BY n DESC"),
                items=db.rows(f"SELECT * FROM audit_exception_queue {w} ORDER BY exception_id LIMIT ? OFFSET ?", p + [limit, offset]))


def evaluation():
    m = db.report("evaluation_metrics")
    return dict(recommendation_quality=m["recommendation_quality"], mastery_quality=m["mastery_quality"],
                outcomes_by_reason_code=m["outcomes_by_reason_code"], detection=m["detection"], distributions=m["distributions"],
                reason_codes=REASON_CODES)
