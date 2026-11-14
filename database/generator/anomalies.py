"""Step 5: inject labelled edge cases on top of the valid baseline.

Each injector changes only its own target rows (targets are disjoint and chosen so no unrelated row is
disturbed) and appends a ground-truth label describing the rule that must catch it.
"""
import random
from backend.engine import replay, target_difficulty, _rationale
from backend.config import MASTERED_AT, REMEDIATE_BELOW, LOOP_DETECT_REPEATS
from .config import DAY, AS_OF
from . import ids


def _gt(gt, etype, eid, issue, rule, decision, context):
    gt.append(dict(gt_id=None, entity_type=etype, entity_id=eid, issue_type=issue, expected_detection_rule=rule,
                   expected_decision=decision, context=context))


def inject_timestamp_invalid(py, cfg, cat, attempts, recs, paths, learners, gt):
    n = cfg.count(cfg.rate_timestamp_invalid)
    recd = {(r["learner_id"], r["content_id"]) for r in recs}
    created = {p["path_id"]: p["created_at"] for p in paths}
    enrolled = {L["learner_id"]: L["enrolled_at"] for L in learners}
    per_lc = {}
    for a in attempts:
        per_lc[(a["learner_id"], a["content_id"])] = per_lc.get((a["learner_id"], a["content_id"]), 0) + 1
    cands = []
    for i in range(1, len(attempts)):
        a, prev = attempts[i], attempts[i - 1]
        it = cat.items[a["content_id"]]
        if (prev["learner_id"] == a["learner_id"] and a["status"] == "COMPLETED" and not it.assessed and a["rec_tmp"] is None
                and per_lc[(a["learner_id"], a["content_id"])] == 1 and (a["learner_id"], a["content_id"]) not in recd):
            cands.append(i)
    py.shuffle(cands)
    used_learners, done = set(), 0
    for i in cands:
        if done >= n:
            break
        a, prev = attempts[i], attempts[i - 1]
        if a["learner_id"] in used_learners:
            continue
        if done % 2 == 0:                                   # (a) submitted before started
            a["submitted_at"] = a["started_at"] - py.randint(60, 3600)
            ctx = "submitted_at earlier than started_at"
        else:                                               # (b) starts before the previous attempt in counter order
            new = prev["started_at"] - py.randint(60, 3600)
            it = cat.items[a["content_id"]]
            if new < created[a["path_id"]] or new < enrolled[a["learner_id"]] or new < it.published_at:
                continue
            a["started_at"] = new
            ctx = f"started_at earlier than previous attempt {prev['attempt_id']}"
        used_learners.add(a["learner_id"]); done += 1
        _gt(gt, "ATTEMPT", a["attempt_id"], "ATTEMPT_TIMESTAMP_ORDER_INVALID",
            "submitted_at < started_at, or started_at decreases in per-learner attempt counter order",
            "QUARANTINE_ATTEMPT", ctx)


def inject_future_mastery(py, cfg, results, attempts_by_id, gt, exclude_attempts):
    n = cfg.count(cfg.rate_future_mastery)
    cands = [i for i, r in enumerate(results) if r["attempt_id"] not in exclude_attempts]
    for i in sorted(py.sample(cands, min(n, len(cands)))):
        r = results[i]
        sub = attempts_by_id[r["attempt_id"]]["submitted_at"]
        r["computed_at"] = sub - py.randint(3600, 10 * DAY)
        _gt(gt, "ASSESSMENT_RESULT", r["result_id"], "MASTERY_USES_FUTURE_ATTEMPT",
            "AssessmentResult.computed_at < Attempt.submitted_at of its evidence", "RECOMPUTE_MASTERY",
            f"mastery stamped {round((sub - r['computed_at']) / 3600, 1)} h before attempt {r['attempt_id']} was submitted")


def inject_missing_skill(py, cfg, cat, content_skills, n_skills, gt):
    n = cfg.count(cfg.rate_missing_skill)
    pool = sorted(c for c, it in cat.items.items() if it.status == "PUBLISHED")
    for k, cid in enumerate(sorted(py.sample(pool, min(n, len(pool))))):
        bad = ids.skill(n_skills + 9000 + k + 1)          # an ID that does not exist in Skill
        content_skills.append(dict(content_id=cid, skill_id=bad, weight=0.5, is_primary=0, _gt=len(gt)))
        _gt(gt, "CONTENT_SKILL", None, "CONTENT_MAPPED_TO_NONEXISTENT_SKILL", "ContentSkill.skill_id not found in Skill (FK)",
            "REJECT_MAPPING", f"{cid} mapped to unknown {bad}")


def inject_prereq_violation(py, cfg, cat, recs, attempts_by_learner, gt):
    n = cfg.count(cfg.rate_prereq_violation)
    linked = {a["rec_tmp"] for lst in attempts_by_learner.values() for a in lst if a["rec_tmp"] is not None}
    decision = {}
    for r in recs:
        decision.setdefault((r["learner_id"], r["recommended_at"]), set()).add(r["content_id"])
    cands = [i for i, r in enumerate(recs) if r["rank"] >= 2 and r["content_id"] is not None and r["rec_tmp"] not in linked]
    py.shuffle(cands)
    done, used = 0, set()
    for i in cands:
        if done >= n:
            break
        r = recs[i]
        if r["learner_id"] in used:
            continue
        t = r["recommended_at"]
        st = replay(cat, attempts_by_learner.get(r["learner_id"], []), as_of=t)
        course = cat.items[r["content_id"]].course_id
        options = [c for c in cat.course_items[course] if c not in decision[(r["learner_id"], t)]
                   and cat.available(cat.items[c], t) and cat.unmet(cat.items[c], st.mastery, t)]
        if not options:
            continue
        cid = options[py.randrange(len(options))]
        it = cat.items[cid]
        un = cat.unmet(it, st.mastery, t)
        m, nev = st.mastery.get(it.primary, 0.0), st.evidence.get(it.primary, 0)
        td = target_difficulty(m)
        nrules = cat.rules_checked(it, t)
        r.update(content_id=cid, skill_id=it.primary, mastery_snapshot=round(m, 4), target_difficulty=td, prereqs_checked=nrules,
                 rationale=_rationale(r["reason_code"], cat, it, m, nev, td, nrules))
        used.add(r["learner_id"]); done += 1
        _gt(gt, "RECOMMENDATION", ("REC", r["rec_tmp"]), "RECOMMENDATION_VIOLATES_PREREQUISITE",
            "a REQUIRED prerequisite of the recommended item is below min_mastery at recommended_at",
            "BLOCK_RECOMMENDATION", "; ".join(f"{p} needs {mm:.2f}, had {have:.2f}" for p, mm, have in un))


def inject_path_loops(py, cfg, cat, recs, events, paths, summary_last, learners, attempts_by_learner, rec_counter, gt, skip_learners):
    """A path that keeps assigning the same item without any mastery gain (the loop guard was bypassed)."""
    n = cfg.count(cfg.rate_path_loop)
    wd = {L["learner_id"]: L["withdrawn_at"] for L in learners}
    by_learner = {}
    for p in paths:
        by_learner.setdefault(p["learner_id"], []).append(p)
    cands = sorted(lid for lid, lst in attempts_by_learner.items() if lst and lid not in skip_learners
                   and max(a["started_at"] for a in lst) <= AS_OF - 45 * DAY)
    py.shuffle(cands)
    done = 0
    for lid in cands:
        if done >= n:
            break
        lst = attempts_by_learner[lid]
        t0 = max(a["started_at"] for a in lst) + DAY
        if wd[lid] is not None and wd[lid] <= t0 + 7 * DAY:
            continue
        st = replay(cat, lst, as_of=t0)
        for p in by_learner[lid]:
            if summary_last.get(p["path_id"]) == "COMPLETED":
                continue
            opts = [c for c in cat.course_items[p["course_id"]]
                    if cat.available(cat.items[c], t0) and cat.available(cat.items[c], t0 + 6 * DAY)
                    and not cat.unmet(cat.items[c], st.mastery, t0) and st.mastery.get(cat.items[c].primary, 0) < MASTERED_AT]
            if not opts:
                continue
            cid = opts[py.randrange(len(opts))]
            it = cat.items[cid]
            m, nev = st.mastery.get(it.primary, 0.0), st.evidence.get(it.primary, 0)
            reason = ("COLD_START_DIAGNOSTIC" if st.total_evidence == 0 else "REMEDIATE_LOW_MASTERY" if nev >= 2 and m < REMEDIATE_BELOW
                      else "NEXT_IN_SEQUENCE" if nev == 0 else "CONTINUE_PRACTICE")
            td = target_difficulty(m)
            nrules = cat.rules_checked(it, t0)
            score = round(0.45 * (1 - m) + 0.30 * (1 - abs(it.difficulty - td) / 4) + 0.10 * it.assessed
                          + 0.10 * (5 - cat.skills[it.primary]["tier"]) / 4, 4)
            reps = LOOP_DETECT_REPEATS + 1
            for k in range(reps):
                t = t0 + k * DAY + py.randint(0, 3 * 3600)
                rec_counter[0] += 1
                tmp = rec_counter[0]
                recs.append(dict(path_id=p["path_id"], content_id=cid, skill_id=it.primary, rank=1, score=score, reason_code=reason,
                                 rationale=_rationale(reason, cat, it, m, nev, td, nrules), mastery_snapshot=round(m, 4),
                                 target_difficulty=td, prereqs_checked=nrules, rec_tmp=tmp, learner_id=lid, recommended_at=t))
                events.append(dict(path_id=p["path_id"], event_type="STEP_ASSIGNED", event_at=t, from_status=None, to_status=None,
                                   content_id=cid, skill_id=it.primary, rec_tmp=tmp, mastery_snapshot=round(m, 4), order=1))
            done += 1
            _gt(gt, "LEARNING_PATH", p["path_id"], "LEARNER_PATH_LOOPS_WITHOUT_PROGRESS",
                f">= {LOOP_DETECT_REPEATS} consecutive STEP_ASSIGNED events for the same item with mastery gain < 0.02",
                "ESCALATE_TO_INSTRUCTOR", f"{cid} assigned {reps}x from {round(m, 2)} mastery with no attempt")
            break
