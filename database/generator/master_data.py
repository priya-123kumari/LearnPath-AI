"""Step 2a: master data first - Course, Skill, SkillPrerequisite (acyclic skill graph), ContentItem, ContentSkill."""
from .config import (CATALOG_START, DAY, PREREQ_REVISION, PASS_PCT, SKILLS_PER_COURSE, TOPICS_PER_COURSE, TIERS,
                     COURSES_PER_DOMAIN, ts, iso)
from .reference import (DOMAINS, TIER_LABELS, COURSE_LEVELS, FORMATS, FORMAT_MIX, ASSESSED, MAX_SCORE, MINUTES, TITLE_SUFFIX)
from . import ids


def _date(t):
    return iso(t)[:10]


def build_master(rng, cfg):
    courses, skills, prereqs = [], [], []
    grid = {}                                  # (course_idx, tier, topic_idx) -> skill_id
    for ci in range(cfg.courses):
        dom_i, seq = divmod(ci, COURSES_PER_DOMAIN)
        dname, prefix, clist = DOMAINS[dom_i % len(DOMAINS)]
        cycle = dom_i // len(DOMAINS)
        title, topics = clist[seq]
        sfx = f" {cycle + 1}" if cycle else ""
        cid = ids.course(ci + 1)
        courses.append(dict(course_id=cid, course_code=f"{prefix}{cycle + 1 if cycle else ''}-{seq + 1}01", title=title + sfx,
                            domain=dname + sfx, sequence_in_domain=seq + 1, level=COURSE_LEVELS[seq], credits=int(rng.integers(2, 7)),
                            status="ACTIVE", effective_from=_date(CATALOG_START), effective_to=None))
        for tier in range(1, TIERS + 1):
            for j, topic in enumerate(topics):
                sid = ids.skill(len(skills) + 1)
                grid[(ci, tier, j)] = sid
                skills.append(dict(skill_id=sid, course_id=cid, skill_name=f"{TIER_LABELS[tier - 1]} {topic}{sfx}", topic=topic + sfx,
                                   tier=tier, status="ACTIVE", effective_from=_date(CATALOG_START)))
    # ---- prerequisite graph: edges only point to a lower tier or to the previous course => acyclic by construction
    def add(skill, pre, rel, mm, cross, eff_to=None):
        prereqs.append(dict(prerequisite_id=ids.prereq(len(prereqs) + 1), skill_id=skill, prerequisite_skill_id=pre, relation_type=rel,
                            min_mastery=mm, cross_course=int(cross), effective_from=_date(CATALOG_START),
                            effective_to=_date(eff_to) if eff_to else None))
    for ci in range(cfg.courses):
        seq = ci % COURSES_PER_DOMAIN
        for tier in range(1, TIERS + 1):
            for j in range(TOPICS_PER_COURSE):
                sid = grid[(ci, tier, j)]
                if tier > 1:
                    add(sid, grid[(ci, tier - 1, j)], "REQUIRED", 0.7, False)
                    if rng.random() < 0.45:
                        other = int((j + 1 + rng.integers(0, TOPICS_PER_COURSE - 1)) % TOPICS_PER_COURSE)
                        rel = "REQUIRED" if rng.random() < 0.7 else "RECOMMENDED"
                        revised = rel == "REQUIRED" and rng.random() < 0.08     # rule retired mid-year (effective-dated)
                        add(sid, grid[(ci, tier - 1, other)], rel, 0.6, False, PREREQ_REVISION if revised else None)
                elif seq > 0:
                    add(sid, grid[(ci - 1, 3, j)], "REQUIRED", 0.6, True)     # entry skill needs tier-3 of the previous course
    # ---- content items, each mapped to one primary (+ optional secondary) skill of its course
    content, cskills = [], []
    per_course = [cfg.content // cfg.courses + (1 if i < cfg.content % cfg.courses else 0) for i in range(cfg.courses)]
    title_n = {}
    for ci in range(cfg.courses):
        cid = courses[ci]["course_id"]
        cs = [grid[(ci, t, j)] for t in range(1, TIERS + 1) for j in range(TOPICS_PER_COURSE)]
        plan = []
        for s in cs:                                   # every skill gets two guaranteed, published, assessed items
            plan.append((s, "QUIZ", True)); plan.append((s, "EXERCISE", True))
        while len(plan) < per_course[ci]:
            plan.append((cs[int(rng.integers(0, len(cs)))], FORMATS[int(rng.choice(len(FORMATS), p=FORMAT_MIX))], False))
        plan = plan[:per_course[ci]]
        for s, fmt, guaranteed in plan:
            sk = skills[int(s[4:]) - 1]
            tier = sk["tier"]
            n = len(content) + 1
            con_id = ids.content(n)
            k = (s, fmt); title_n[k] = title_n.get(k, 0) + 1
            diff = int(min(5, max(1, round(tier + rng.normal(0, 0.7)))))
            assessed = fmt in ASSESSED
            u = rng.random()
            status, pub, ret = "PUBLISHED", CATALOG_START + int(rng.integers(0, 30 * DAY)), None
            if not guaranteed:
                if u < 0.02:
                    status, pub = "DRAFT", None
                elif u < 0.05:
                    status, ret = "RETIRED", ts(2026, 4, 1) + int(rng.integers(0, 180 * DAY))
                elif u < 0.20:
                    pub = ts(2026, 2, 1) + int(rng.integers(0, 150 * DAY))     # new content released mid-year
            content.append(dict(content_id=con_id, course_id=cid, title=f"{sk['skill_name']}: {TITLE_SUFFIX[fmt]} {title_n[k]}",
                                format=fmt, difficulty=diff, est_minutes=max(3, int(round(MINUTES[fmt] * rng.lognormal(0, 0.25)))),
                                is_assessed=int(assessed), max_score=MAX_SCORE[fmt] if assessed else None,
                                pass_threshold_pct=PASS_PCT if assessed else None, status=status, published_at=pub, retired_at=ret))
            cskills.append(dict(content_id=con_id, skill_id=s, weight=1.0, is_primary=1))
            if rng.random() < 0.35:
                j = cs.index(s) % TOPICS_PER_COURSE
                if tier > 1 and rng.random() < 0.5:
                    sec = grid[(ci, tier - 1, j)]
                else:
                    sec = grid[(ci, tier, (j + 1 + int(rng.integers(0, TOPICS_PER_COURSE - 1))) % TOPICS_PER_COURSE)]
                cskills.append(dict(content_id=con_id, skill_id=sec, weight=0.5, is_primary=0))
    # coverage gap (exception path): per course, every item of one tier-2 skill is retired for revision from August
    # with no replacement, so some learners end up with nothing eligible and are escalated to an instructor.
    by_primary = {}
    for c, m in zip(content, [x for x in cskills if x["is_primary"]]):
        by_primary.setdefault(m["skill_id"], []).append(c)
    for ci in range(cfg.courses):
        gap_skill = grid[(ci, 2, int(rng.integers(0, TOPICS_PER_COURSE)))]
        for c in by_primary.get(gap_skill, []):
            if c["status"] != "DRAFT":
                c["status"], c["retired_at"] = "RETIRED", ts(2026, 8, 1) + int(rng.integers(0, 10 * DAY))
                if c["published_at"] >= c["retired_at"]:
                    c["published_at"] = CATALOG_START
    return dict(courses=courses, skills=skills, prereqs=prereqs, content=content, content_skills=cskills, grid=grid)
