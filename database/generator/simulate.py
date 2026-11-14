"""Step 2b: dependent transactions/events - Learner, LearningPath, Attempt, AssessmentResult, Recommendation, path events.

Each learner has hidden traits (ability, learning rate, true skill mastery). At each study session the backend
recommender ranks next activities from the learner's *observed* evidence only; the learner usually follows it,
sometimes retries a failed item or wanders off-path (which creates natural prerequisite gaps). Scores come from
the hidden true mastery, so outcomes follow documented rules rather than independent random labels.
Recommendation outcomes and path statuses are derived later (derive.py) from the final attempt records.
"""
import math
import random
from backend.engine import LearnerState, recommend, target_difficulty
from backend.config import MASTERED_AT
from .config import TIMELINE_START, AS_OF, DAY, MAX_PATHS, COURSES_PER_DOMAIN, iso
from .reference import (PRIOR_LEVELS, PRIOR_MIX, COUNTRIES, COUNTRY_MIX, FIRST, LAST, MINUTES, LEARNING_GAIN)
from . import ids

STEP, MASTER, STATUS = 1, 2, 3          # same-timestamp ordering of path events (CREATED = 0)


def _alloc(total, weights):
    """Largest-remainder rounding: integer budgets that sum exactly to `total`."""
    s = sum(weights)
    raw = [total * w / s for w in weights]
    base = [int(math.floor(x)) for x in raw]
    rest = total - sum(base)
    order = sorted(range(len(raw)), key=lambda i: (-(raw[i] - base[i]), i))
    for i in order[:rest]:
        base[i] += 1
    return base


def build_learners(rng, cfg):
    n = cfg.learners
    py = random.Random(int(rng.integers(2 ** 62)))
    cold = set(int(i) for i in rng.choice(n, size=int(round(n * cfg.cold_start_share)), replace=False))
    learners, traits = [], []
    span_total = AS_OF - TIMELINE_START
    for i in range(n):
        lid = ids.learner(i + 1)
        prior = PRIOR_LEVELS[int(rng.choice(3, p=PRIOR_MIX))]
        # enrolments are front-loaded in the year; cold-start learners can enrol until the last day
        frac = float(rng.beta(1.2, 2.2)) if i not in cold else float(rng.random())
        latest = AS_OF - (2 * DAY if i in cold else 21 * DAY)
        enrolled = min(latest, TIMELINE_START + int(frac * span_total))
        enrolled -= enrolled % 60
        month = int(iso(enrolled)[5:7])
        learners.append(dict(learner_id=lid, display_name=f"{py.choice(FIRST)} {py.choice(LAST)}", email=f"learner{i + 1:06d}@example.edu",
                             country=COUNTRIES[int(rng.choice(len(COUNTRIES), p=COUNTRY_MIX))], prior_level=prior,
                             cohort=f"2026-Q{(month - 1) // 3 + 1}", enrolled_at=enrolled, status="ACTIVE", withdrawn_at=None))
        theta = float(rng.normal({"NOVICE": -0.4, "INTERMEDIATE": 0.2, "ADVANCED": 0.6}[prior], 0.8))
        traits.append(dict(theta=theta, lr=float(rng.uniform(0.10, 0.22)), cold=i in cold,
                           withdraw=(i not in cold) and rng.random() < cfg.withdraw_share,
                           sess_size=float(rng.uniform(2.5, 5.0)), activity=float(rng.lognormal(0, 0.9))))
    # attempt budgets: sum exactly to cfg.attempts; weighted by activity and by the time left in the year
    w = []
    for L, tr in zip(learners, traits):
        if tr["cold"]:
            w.append(0.0); continue
        days = (AS_OF - L["enrolled_at"]) / DAY
        w.append(tr["activity"] * (days / 300) ** 0.7)
    active = [i for i in range(n) if w[i] > 0]
    budgets = [0] * n
    alloc = _alloc(cfg.attempts - len(active), [w[i] for i in active])     # everyone active gets >= 1 attempt
    for i, b in zip(active, alloc):
        budgets[i] = b + 1
    cap = lambda i: max(1, int((AS_OF - learners[i]["enrolled_at"]) / DAY * 6))   # <= 6 attempts per available day
    for _ in range(10):
        over = sum(max(0, budgets[i] - cap(i)) for i in active)
        if not over:
            break
        for i in active:
            budgets[i] = min(budgets[i], cap(i))
        room = [i for i in active if budgets[i] < cap(i)]
        add = _alloc(over, [w[i] for i in room])
        for i, a in zip(room, add):
            budgets[i] += a
    for tr, b in zip(traits, budgets):
        tr["budget"] = b
    return learners, traits


def _sigmoid(x):
    return 1 / (1 + math.exp(-x))


def simulate(rng, cfg, cat, master, learners, traits):
    py = random.Random(int(rng.integers(2 ** 62)))
    courses = master["courses"]
    domain_courses = {}
    for c in courses:
        domain_courses.setdefault(c["domain"], []).append(c["course_id"])
    domains = sorted(domain_courses)
    attempts, results, recs, events, paths = [], [], [], [], []
    true_rows = []
    rec_counter = [0]
    states = {}

    for L, tr in zip(learners, traits):
        lid = L["learner_id"]
        st = LearnerState()
        k_true = {}
        dom = domains[py.randrange(len(domains))]
        dc = domain_courses[dom]
        prior = L["prior_level"]
        c0 = 0 if prior == "NOVICE" else (py.random() < 0.3) * 1 if prior == "INTERMEDIATE" else 1 + (py.random() < 0.5)
        c0 = min(c0, len(dc) - 1)
        # hidden prior knowledge of earlier courses in the domain (estimated mastery still starts at 0 = cold start)
        for ci in range(c0 + 1):
            for sid in cat.course_skills[dc[ci]]:
                tier = cat.skills[sid]["tier"]
                if ci < c0:
                    k_true[sid] = py.uniform(0.55, 0.9) if tier <= 3 else py.uniform(0.2, 0.5)
                elif prior != "NOVICE" and tier == 1:
                    k_true[sid] = py.uniform(0.1, 0.4)
        enrolled = L["enrolled_at"]
        pstate = {}                       # path_id -> dict(course, created, mastered:set, completed_at)
        open_paths = []

        def new_path(course, t):
            pid = ids.path(len(paths) + 1)
            paths.append(dict(path_id=pid, learner_id=lid, course_id=course, created_at=t))
            pstate[pid] = dict(course=course, mastered=set(), completed_at=None)
            open_paths.append((pid, course))
            events.append(dict(path_id=pid, event_type="PATH_CREATED", event_at=t, from_status=None, to_status="ACTIVE", content_id=None,
                               skill_id=None, rec_tmp=None, mastery_snapshot=None, order=0))
            for sid in cat.course_skills[course]:          # carry-over credit for skills already mastered
                if st.mastery.get(sid, 0) >= MASTERED_AT:
                    mark_mastered(pid, sid, t)
            return pid

        def mark_mastered(pid, sid, t):
            ps = pstate[pid]
            if sid in ps["mastered"]:
                return
            ps["mastered"].add(sid)
            events.append(dict(path_id=pid, event_type="SKILL_MASTERED", event_at=t, from_status=None, to_status=None, content_id=None,
                               skill_id=sid, rec_tmp=None, mastery_snapshot=st.mastery.get(sid, 0.0), order=MASTER))
            if len(ps["mastered"]) == len(cat.course_skills[ps["course"]]) and ps["completed_at"] is None:
                ps["completed_at"] = t
                open_paths[:] = [p for p in open_paths if p[0] != pid]

        course_path = {}
        course_path[dc[c0]] = new_path(dc[c0], enrolled)
        budget = tr["budget"]
        # ---- session plan
        end_at = AS_OF - 2 * 3600
        if tr["withdraw"]:
            end_at = enrolled + int((AS_OF - enrolled) * py.uniform(0.25, 0.75))
        if budget == 0:
            sessions = [(enrolled + 120, 0)]                 # cold start: one diagnostic recommendation, never acted on
        else:
            n_s = max(1, int(round(budget / tr["sess_size"])))
            n_s = min(n_s, budget)
            sizes = [1] * n_s
            for _ in range(budget - n_s):
                sizes[py.randrange(n_s)] += 1
            first = enrolled + py.randint(600, 3 * DAY)
            starts = sorted(py.randint(first, max(first + 1, end_at - 4 * 3600)) for _ in range(n_s - 1))
            sessions = list(zip([first] + starts, sizes))
        seq, att_no, cursor = 0, {}, enrolled
        last_any = None
        for s_start, size in sessions:
            t = max(s_start, cursor + 20 * 60)
            # enrol in the next course of the domain once half of the current one is mastered
            last_course = paths[-1]["course_id"] if paths[-1]["learner_id"] == lid else None
            ci = dc.index(last_course)
            lp = course_path[last_course]
            if (len(pstate[lp]["mastered"]) >= 6 and ci + 1 < len(dc) and len(pstate) < MAX_PATHS and py.random() < 0.5):
                course_path[dc[ci + 1]] = new_path(dc[ci + 1], t)
            res = recommend(cat, st, list(open_paths), t)
            queue = []
            for r in res["recs"]:
                rec_counter[0] += 1
                tmp = rec_counter[0]
                recs.append(dict(r, rec_tmp=tmp, learner_id=lid, recommended_at=t))
                if r["content_id"] is not None:
                    queue.append((tmp, r["content_id"], r["path_id"]))
            if not res["escalated"]:
                top = res["recs"][0]
                st.record_step(top["path_id"], top["content_id"], top["skill_id"])
                events.append(dict(path_id=top["path_id"], event_type="STEP_ASSIGNED", event_at=t, from_status=None, to_status=None,
                                   content_id=top["content_id"], skill_id=top["skill_id"], rec_tmp=recs[-len(res["recs"])]["rec_tmp"],
                                   mastery_snapshot=top["mastery_snapshot"], order=STEP))
            cursor = t + py.randint(30, 180)
            last_failed = None
            for _ in range(size):
                # ---- choose the activity
                cid = None
                if (last_failed is not None and st.item_stats.get(last_failed, (0, 0, 0))[2] < 3 and py.random() < cfg.retry_prob
                        and cat.available(cat.items[last_failed], cursor)):
                    cid = last_failed
                elif queue and py.random() < cfg.follow_prob and cat.available(cat.items[queue[0][1]], cursor):
                    cid = queue[0][1]
                else:
                    # off-path browsing: the learner's courses plus courses the engine pointed to this session
                    pool = sorted({c for _, c in open_paths} | {cat.items[r["content_id"]].course_id for r in res["recs"] if r["content_id"]})
                    pool = pool or [paths[-1]["course_id"]]
                    draws = []
                    for _ in range(6):
                        c = cat.course_items[pool[py.randrange(len(pool))]]
                        cand = cat.items[c[py.randrange(len(c))]]
                        if cat.available(cand, cursor):
                            draws.append(cand)
                    open_ = [d for d in draws if not cat.unmet(d, st.mastery, cursor)]
                    if open_:
                        cid = open_[0].content_id
                    elif draws and py.random() < 0.3:              # sometimes jumps ahead to locked content (prerequisite gap)
                        cid = draws[0].content_id
                    elif queue:
                        cid = queue[0][1]
                    else:                                          # first available item of the learner's courses
                        cc = [x for c in pool for x in cat.course_items[c] if cat.available(cat.items[x], cursor)]
                        cid = (draws[0].content_id if draws else cc[0])
                link = next((q for q in queue if q[1] == cid), None)
                if link:
                    queue.remove(link)
                it = cat.items[cid]
                if link:
                    pid = link[2]
                else:
                    pid = course_path.get(it.course_id) or (open_paths[0][0] if open_paths else course_path[paths[-1]["course_id"]])
                # ---- simulate the attempt from hidden true mastery
                req = [(p, mm) for s, _ in it.skills for p, mm in cat.required(s, cursor)]
                gap = (sum(max(0.0, mm - k_true.get(p, 0.0)) for p, mm in req) / len(req)) if req else 0.0
                k_item = sum(k_true.get(s, 0.0) * w for s, w in it.skills) / sum(w for _, w in it.skills)
                p_ok = _sigmoid(5 * (0.75 * k_item + 0.12 * tr["theta"] + 0.15 - 0.12 * (it.difficulty - 1) - 0.6 * gap))
                abandoned = py.random() < cfg.abandon_prob
                full = max(60, int(MINUTES[it.format] * 60 * py.lognormvariate(0, 0.35)))
                seq += 1
                att_no[cid] = att_no.get(cid, 0) + 1
                aid = ids.attempt(lid, seq)
                started = cursor
                if abandoned:
                    dur = max(30, int(full * py.uniform(0.05, 0.9)))
                    submitted, raw, mx, sp, passed, comp, status = None, None, None, None, None, round(py.uniform(5, 90), 1), "ABANDONED"
                else:
                    dur = full
                    submitted, status, comp = started + dur, "COMPLETED", 100.0
                    if it.assessed:
                        mx = it.max_score
                        raw = int(round(min(1.0, max(0.0, p_ok + py.gauss(0, 0.08))) * mx))
                        sp = round(100.0 * raw / mx, 2)
                        passed = int(sp >= 70.0)
                    else:
                        raw = mx = sp = passed = None
                attempts.append(dict(attempt_id=aid, learner_id=lid, content_id=cid, path_id=pid, rec_tmp=link[0] if link else None,
                                     attempt_no=att_no[cid], started_at=started, submitted_at=submitted, duration_sec=dur, status=status,
                                     raw_score=raw, max_score=mx, score_pct=sp, passed=passed, completion_pct=comp))
                # ---- hidden learning
                for s, w in it.skills:
                    k = k_true.get(s, 0.0)
                    k_true[s] = min(0.99, k + tr["lr"] * w * LEARNING_GAIN[it.format] * (1 - k) * (0.3 + 0.7 * p_ok) * (1 - min(gap, 0.6))
                                    * (0.2 if abandoned else 1.0))
                # ---- observed evidence -> mastery (backend engine) -> results and mastered events
                t_ev = submitted if submitted is not None else started + dur
                for e in st.apply_attempt(cat, it, status, sp, bool(passed), t_ev):
                    results.append(dict(e, attempt_id=aid, learner_id=lid, content_id=cid, score_pct=sp,
                                        computed_at=submitted + py.randint(1, 90), model_version="EWMA-1.0"))
                    if e["mastery_after"] >= MASTERED_AT:
                        cp = course_path.get(cat.skills[e["skill_id"]]["course_id"])
                        if cp:
                            mark_mastered(cp, e["skill_id"], submitted)
                last_failed = cid if (it.assessed and status == "COMPLETED" and not passed) else None
                cursor = started + dur + py.randint(30, 8 * 60)
                last_any = started
        if tr["withdraw"] and last_any is not None:
            wd = last_any + py.randint(20 * DAY, 45 * DAY)
            if wd <= AS_OF:
                L["status"], L["withdrawn_at"] = "WITHDRAWN", wd
        for sid in sorted(k_true):
            true_rows.append(dict(learner_id=lid, skill_id=sid, true_mastery=round(k_true[sid], 4)))
        states[lid] = dict(paths=pstate)
    return dict(attempts=attempts, results=results, recs=recs, events=events, paths=paths, true_mastery=true_rows, states=states)
