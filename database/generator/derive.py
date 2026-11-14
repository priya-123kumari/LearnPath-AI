"""Step 6: derived values computed from source records (never generated independently).

* Recommendation status/outcome  <- first attempt on the recommended item within 14 days
* LearningPath status events     <- attempt activity gaps (30 days -> STALLED), mastery events (COMPLETED), withdrawal (ABANDONED)
* LearningPath summary columns   <- the path's events and attempts
The validator calls the same rules on the exported tables to prove the stored values reconcile.
"""
from bisect import bisect_left
from .config import DAY, AS_OF, OUTCOME_WINDOW_DAYS, STALL_AFTER_DAYS

STATUS_ORDER = 3


def _n(v):
    return None if v is None or (isinstance(v, float) and v != v) else v


def rec_outcomes(recs, attempts):
    """recs/attempts: lists of dicts with epoch-int times. Returns {rec key: outcome fields}; key = rec['_key']."""
    by_lc = {}
    for a in attempts:
        by_lc.setdefault((a["learner_id"], a["content_id"]), []).append((a["started_at"], a["attempt_id"], a))
    for v in by_lc.values():
        v.sort(key=lambda x: (x[0], x[1]))
    out = {}
    win = OUTCOME_WINDOW_DAYS * DAY
    for r in recs:
        key = r["_key"]
        if _n(r["content_id"]) is None:
            out[key] = dict(status="ESCALATED", outcome="ESCALATED", outcome_attempt_id=None, outcome_score_pct=None, outcome_at=None)
            continue
        lst = by_lc.get((r["learner_id"], r["content_id"]), [])
        i = bisect_left(lst, (r["recommended_at"], ""))
        hit = lst[i][2] if i < len(lst) and lst[i][0] <= r["recommended_at"] + win else None
        if hit is None:
            done = r["recommended_at"] + win <= AS_OF
            out[key] = dict(status="EXPIRED" if done else "ISSUED", outcome="NOT_ATTEMPTED" if done else "PENDING",
                            outcome_attempt_id=None, outcome_score_pct=None, outcome_at=None)
            continue
        if hit["status"] == "ABANDONED":
            oc = "ABANDONED"
        elif _n(hit["score_pct"]) is None:
            oc = "COMPLETED_UNSCORED"
        else:
            oc = "COMPLETED_PASS" if hit["passed"] else "COMPLETED_FAIL"
        out[key] = dict(status="ACCEPTED", outcome=oc, outcome_attempt_id=hit["attempt_id"],
                        outcome_score_pct=_n(hit["score_pct"]), outcome_at=hit["started_at"])
    return out


def path_status(path, activity, completed_at, withdrawn_at):
    """Status events for one path. activity = sorted attempt start times on the path."""
    created = path["created_at"]
    evs, last, status = [], created, "ACTIVE"
    stall = STALL_AFTER_DAYS * DAY
    for t in activity:
        if completed_at is not None and t > completed_at:
            break
        if t - last > stall:
            evs.append((last + stall, "ACTIVE", "STALLED"))
            evs.append((t, "STALLED", "ACTIVE"))
        last = max(last, t)
    if completed_at is not None:
        evs.append((completed_at, "ACTIVE", "COMPLETED"))
    else:
        end = withdrawn_at if withdrawn_at is not None else AS_OF
        cur = "ACTIVE"
        if end - last > stall:
            evs.append((last + stall, "ACTIVE", "STALLED")); cur = "STALLED"
        if withdrawn_at is not None:
            evs.append((withdrawn_at, cur, "ABANDONED"))
    return evs


def derive_paths(paths, events, attempts, learners, skills_per_course):
    """Returns (status_events, summary by path_id). `events` must not contain STATUS_CHANGED rows yet."""
    act = {}
    for a in attempts:
        act.setdefault(a["path_id"], []).append(a["started_at"])
    mastered = {}
    for e in events:
        if e["event_type"] == "SKILL_MASTERED":
            mastered.setdefault(e["path_id"], []).append(e["event_at"])
    wd = {L["learner_id"]: _n(L["withdrawn_at"]) for L in learners}
    status_events, summary = [], {}
    for p in paths:
        pid = p["path_id"]
        total = skills_per_course[p["course_id"]]
        ms = sorted(mastered.get(pid, []))
        completed_at = ms[total - 1] if len(ms) >= total else None
        acts = sorted(act.get(pid, []))
        evs = path_status(p, acts, completed_at, wd[p["learner_id"]])
        for t, f, to in evs:
            status_events.append(dict(path_id=pid, event_type="STATUS_CHANGED", event_at=t, from_status=f, to_status=to, content_id=None,
                                      skill_id=None, rec_tmp=None, mastery_snapshot=None, order=STATUS_ORDER))
        status, changed = ("ACTIVE", p["created_at"]) if not evs else (evs[-1][2], evs[-1][0])
        summary[pid] = dict(status=status, status_changed_at=changed, skills_total=total, skills_mastered=len(ms),
                            progress_pct=round(100.0 * len(ms) / total, 1), last_activity_at=acts[-1] if acts else None,
                            completed_at=completed_at)
    return status_events, summary
