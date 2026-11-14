"""Single source of truth for the data model.

Drives: CSV/JSON column order, SQL DDL, enum validation and docs/data_dictionary.md.
Column tuple: (name, type, required, allowed, unit, unique, rule, fk)
types: TEXT | INTEGER | REAL | DATE | TIMESTAMP | BOOLEAN   (BOOLEAN exported as 0/1, TIMESTAMP as ISO-8601 UTC 'Z')
"""
from collections import OrderedDict
from .reference import FORMATS, REASON_CODES, PRIOR_LEVELS, COUNTRIES

PATH_STATUSES = ["ACTIVE", "STALLED", "COMPLETED", "ABANDONED"]
# legal lifecycle transitions for LearningPath (None = creation)
TRANSITIONS = {
    None: ["ACTIVE"],
    "ACTIVE": ["STALLED", "COMPLETED", "ABANDONED"],
    "STALLED": ["ACTIVE", "ABANDONED"],
    "COMPLETED": [], "ABANDONED": [],
}
PATH_EVENT_TYPES = ["PATH_CREATED", "STEP_ASSIGNED", "SKILL_MASTERED", "STATUS_CHANGED"]
REC_STATUSES = ["ISSUED", "ACCEPTED", "EXPIRED", "ESCALATED"]
REC_OUTCOMES = ["PENDING", "NOT_ATTEMPTED", "COMPLETED_PASS", "COMPLETED_FAIL", "COMPLETED_UNSCORED", "ABANDONED", "ESCALATED"]
MASTERY_LEVELS = ["NOT_STARTED", "DEVELOPING", "PROFICIENT", "MASTERED"]
ISSUE_TYPES = ["RECOMMENDATION_VIOLATES_PREREQUISITE", "ATTEMPT_TIMESTAMP_ORDER_INVALID",
               "CONTENT_MAPPED_TO_NONEXISTENT_SKILL", "MASTERY_USES_FUTURE_ATTEMPT",
               "LEARNER_PATH_LOOPS_WITHOUT_PROGRESS"]

C = lambda name, typ, req=True, allowed=None, unit=None, uniq=False, rule="", fk=None: (name, typ, req, allowed, unit, uniq, rule, fk)

SCHEMA = OrderedDict()


def table(name, file, pk, desc, card, cols):
    SCHEMA[name] = dict(file=file, pk=pk, desc=desc, cardinality=card, cols=cols)


# ------------------------------------------------------------------ master data
table("Learner", "learners", ["learner_id"], "Learner master record. Progress lives in events (attempts, results, path events), never on this row.",
      "Learner 1:N LearningPath; Learner 1:N Attempt; Learner 1:N AssessmentResult; Learner 1:N Recommendation",
      [C("learner_id", "TEXT", uniq=True, rule="^LRN-\\d{6}$"),
       C("display_name", "TEXT", rule="synthetic name, not a real person"),
       C("email", "TEXT", uniq=True, rule="learnerNNNNNN@example.edu (reserved domain)"),
       C("country", "TEXT", allowed=COUNTRIES, rule="ISO-3166 alpha-2"),
       C("prior_level", "TEXT", allowed=PRIOR_LEVELS, rule="self-reported at enrolment; sets the starting course"),
       C("cohort", "TEXT", allowed=["2026-Q1", "2026-Q2", "2026-Q3", "2026-Q4"], rule="= quarter of enrolled_at"),
       C("enrolled_at", "TIMESTAMP", rule="2026-01-05 .. AS_OF"),
       C("status", "TEXT", allowed=["ACTIVE", "WITHDRAWN"]),
       C("withdrawn_at", "TIMESTAMP", False, rule="set iff WITHDRAWN; > last attempt; <= AS_OF")])
table("Course", "courses", ["course_id"], "Course (master data). 5 courses per domain in learning order; each owns 20 skills.",
      "Course 1:N Skill; Course 1:N ContentItem; Course 1:N LearningPath",
      [C("course_id", "TEXT", uniq=True, rule="^CRS-\\d{6}$"), C("course_code", "TEXT", uniq=True, rule="<domain prefix>-<seq>01, e.g. DS-301"),
       C("title", "TEXT"), C("domain", "TEXT"), C("sequence_in_domain", "INTEGER", rule="1..5; course n builds on course n-1"),
       C("level", "TEXT", allowed=["INTRODUCTORY", "INTERMEDIATE", "ADVANCED"]), C("credits", "INTEGER", unit="credits", rule="2..6"),
       C("status", "TEXT", allowed=["ACTIVE", "ARCHIVED"]), C("effective_from", "DATE"), C("effective_to", "DATE", False, rule=">= effective_from")])
table("Skill", "skills", ["skill_id"], "Skill node of the prerequisite graph. Each course covers 4 topics x 5 tiers.",
      "Course 1:N Skill; Skill N:M Skill via SkillPrerequisite; Skill N:M ContentItem via ContentSkill",
      [C("skill_id", "TEXT", uniq=True, rule="^SKL-\\d{6}$"), C("course_id", "TEXT", fk="Course.course_id"),
       C("skill_name", "TEXT", uniq=True, rule="<tier label> <topic>"), C("topic", "TEXT"),
       C("tier", "INTEGER", allowed=[1, 2, 3, 4, 5], rule="1 = foundations .. 5 = expert"),
       C("status", "TEXT", allowed=["ACTIVE", "DEPRECATED"]), C("effective_from", "DATE")])
table("SkillPrerequisite", "skill_prerequisites", ["prerequisite_id"],
      "Directed, effective-dated edge of the skill graph: prerequisite_skill_id must reach min_mastery before skill_id is eligible.",
      "Skill N:M Skill (bridge). Graph must be acyclic.",
      [C("prerequisite_id", "TEXT", uniq=True, rule="^SPR-\\d{6}$"), C("skill_id", "TEXT", fk="Skill.skill_id"),
       C("prerequisite_skill_id", "TEXT", fk="Skill.skill_id", rule="!= skill_id; lower tier in same course, or tier 3 of the previous course"),
       C("relation_type", "TEXT", allowed=["REQUIRED", "RECOMMENDED"], rule="only REQUIRED rules gate eligibility"),
       C("min_mastery", "REAL", unit="mastery 0..1", rule="0.6 or 0.7"),
       C("cross_course", "BOOLEAN", rule="1 iff the two skills belong to different courses"),
       C("effective_from", "DATE"), C("effective_to", "DATE", False, rule=">= effective_from; null = still in force")])
table("ContentItem", "content_items", ["content_id"], "Learning activity (video, reading, quiz, exercise, interactive lab, project).",
      "Course 1:N ContentItem; ContentItem N:M Skill via ContentSkill; ContentItem 1:N Attempt",
      [C("content_id", "TEXT", uniq=True, rule="^CNT-\\d{6}$"), C("course_id", "TEXT", fk="Course.course_id"),
       C("title", "TEXT"), C("format", "TEXT", allowed=FORMATS),
       C("difficulty", "INTEGER", allowed=[1, 2, 3, 4, 5], rule="~ tier of primary skill +/- 1"),
       C("est_minutes", "INTEGER", unit="minutes", rule="> 0"),
       C("is_assessed", "BOOLEAN", rule="1 iff format in QUIZ, EXERCISE, INTERACTIVE, PROJECT"),
       C("max_score", "INTEGER", False, unit="points", rule="set iff is_assessed"),
       C("pass_threshold_pct", "REAL", False, unit="%", rule="70 iff is_assessed"),
       C("status", "TEXT", allowed=["DRAFT", "PUBLISHED", "RETIRED"]),
       C("published_at", "TIMESTAMP", False, rule="null iff DRAFT"),
       C("retired_at", "TIMESTAMP", False, rule="set iff RETIRED; > published_at")])
table("ContentSkill", "content_skills", ["content_skill_id"], "Bridge table for the N:M relationship ContentItem <-> Skill.",
      "ContentItem N:M Skill (each item has exactly one primary skill)",
      [C("content_skill_id", "TEXT", uniq=True, rule="^CSK-\\d{6}$"), C("content_id", "TEXT", fk="ContentItem.content_id"),
       C("skill_id", "TEXT", fk="Skill.skill_id", rule="skill of the same course"),
       C("weight", "REAL", rule="1.0 primary, 0.5 secondary"), C("is_primary", "BOOLEAN", rule="exactly one primary per content item")])
# ------------------------------------------------------------------ transactions / events
table("LearningPath", "learning_paths", ["path_id"], "A learner's enrolment in one course. Status and progress are DERIVED from LearningPathEvent.",
      "Learner 1:N LearningPath; Course 1:N LearningPath; LearningPath 1:N LearningPathEvent / Attempt / Recommendation",
      [C("path_id", "TEXT", uniq=True, rule="^PATH-2026-\\d{6}$"), C("learner_id", "TEXT", fk="Learner.learner_id"),
       C("course_id", "TEXT", fk="Course.course_id", rule="unique per learner"),
       C("created_at", "TIMESTAMP", rule=">= Learner.enrolled_at"),
       C("status", "TEXT", allowed=PATH_STATUSES, rule="= to_status of last STATUS event"),
       C("status_changed_at", "TIMESTAMP", rule="= event_at of last STATUS event"),
       C("skills_total", "INTEGER", rule="= skills in course"),
       C("skills_mastered", "INTEGER", rule="= count of SKILL_MASTERED events"),
       C("progress_pct", "REAL", unit="%", rule="= round(100 * skills_mastered / skills_total, 1)"),
       C("last_activity_at", "TIMESTAMP", False, rule="= max(started_at) of the path's attempts"),
       C("completed_at", "TIMESTAMP", False, rule="set iff COMPLETED")])
table("LearningPathEvent", "learning_path_events", ["event_id"],
      "Append-only path history: creation, every assigned step, each newly mastered skill and every status change.",
      "LearningPath 1:N LearningPathEvent; Recommendation 0..1:1 STEP_ASSIGNED event",
      [C("event_id", "TEXT", uniq=True, rule="^PEV-\\d{8}$"), C("path_id", "TEXT", fk="LearningPath.path_id"),
       C("event_seq", "INTEGER", rule="1..n contiguous per path, ordered by event_at"),
       C("event_type", "TEXT", allowed=PATH_EVENT_TYPES), C("event_at", "TIMESTAMP", rule="non-decreasing per path"),
       C("from_status", "TEXT", False, allowed=PATH_STATUSES, rule="STATUS_CHANGED only"),
       C("to_status", "TEXT", False, allowed=PATH_STATUSES, rule="PATH_CREATED / STATUS_CHANGED; legal transition"),
       C("content_id", "TEXT", False, fk="ContentItem.content_id", rule="STEP_ASSIGNED only"),
       C("skill_id", "TEXT", False, fk="Skill.skill_id", rule="STEP_ASSIGNED / SKILL_MASTERED"),
       C("recommendation_id", "TEXT", False, fk="Recommendation.recommendation_id", rule="STEP_ASSIGNED: rank-1 recommendation"),
       C("mastery_snapshot", "REAL", False, unit="mastery 0..1", rule="skill mastery when the event happened")])
table("Attempt", "attempts", ["attempt_id"], "One learner attempt at one content item. Counter is chronological per learner.",
      "Learner 1:N Attempt; ContentItem 1:N Attempt; LearningPath 1:N Attempt; Recommendation 0..1:N Attempt; Attempt 1:N AssessmentResult",
      [C("attempt_id", "TEXT", uniq=True, rule="^ATT-LRN-\\d{6}-\\d{6}$ i.e. ATT-<learner-id>-<seq>; seq order = started_at order"),
       C("learner_id", "TEXT", fk="Learner.learner_id", rule="= learner in attempt_id"),
       C("content_id", "TEXT", fk="ContentItem.content_id", rule="published at started_at"),
       C("path_id", "TEXT", fk="LearningPath.path_id", rule="path of the same learner"),
       C("recommendation_id", "TEXT", False, fk="Recommendation.recommendation_id", rule="set when the learner followed a recommendation"),
       C("attempt_no", "INTEGER", rule="1..n contiguous per learner + content (repeated attempts)"),
       C("started_at", "TIMESTAMP", rule=">= enrolled_at; <= AS_OF"),
       C("submitted_at", "TIMESTAMP", False, rule="null iff ABANDONED; >= started_at"),
       C("duration_sec", "INTEGER", unit="seconds", rule="= submitted_at - started_at (abandoned: time until leaving)"),
       C("status", "TEXT", allowed=["COMPLETED", "ABANDONED"]),
       C("raw_score", "INTEGER", False, unit="points", rule="set iff COMPLETED and assessed; 0..max_score"),
       C("max_score", "INTEGER", False, unit="points", rule="= ContentItem.max_score"),
       C("score_pct", "REAL", False, unit="%", rule="= round(100 * raw_score / max_score, 2)"),
       C("passed", "BOOLEAN", False, rule="= score_pct >= pass_threshold_pct"),
       C("completion_pct", "REAL", unit="%", rule="100 if COMPLETED, else 5..90")])
table("AssessmentResult", "assessment_results", ["result_id"],
      "Append-only mastery evidence: one row per (assessed, completed attempt x mapped skill). Mastery is replayable from attempts.",
      "Attempt 1:N AssessmentResult; Skill 1:N AssessmentResult",
      [C("result_id", "TEXT", uniq=True, rule="^ASR-\\d{8}$"), C("attempt_id", "TEXT", fk="Attempt.attempt_id"),
       C("learner_id", "TEXT", fk="Learner.learner_id"), C("skill_id", "TEXT", fk="Skill.skill_id"),
       C("content_id", "TEXT", fk="ContentItem.content_id"),
       C("evidence_weight", "REAL", rule="ContentSkill.weight x format weight (QUIZ .70, EXERCISE .85, INTERACTIVE .60, PROJECT 1.0)"),
       C("score_pct", "REAL", unit="%", rule="= Attempt.score_pct"),
       C("mastery_before", "REAL", unit="mastery 0..1", rule="= previous mastery_after for learner+skill, 0 for first"),
       C("mastery_after", "REAL", unit="mastery 0..1",
         rule="round(before + 0.40*w*(min(1, s*(0.8+0.05*difficulty)) - before), 4), s = score_pct/100"),
       C("evidence_count", "INTEGER", rule="1..n per learner+skill"),
       C("mastery_level", "TEXT", allowed=MASTERY_LEVELS, rule="DEVELOPING <0.5 <= PROFICIENT < 0.8 <= MASTERED"),
       C("computed_at", "TIMESTAMP", rule=">= Attempt.submitted_at (must not use future evidence)"),
       C("model_version", "TEXT", allowed=["EWMA-1.0"])])
table("Recommendation", "recommendations", ["recommendation_id"],
      "Ranked next-activity recommendation with reason code, rationale and the outcome observed afterwards.",
      "Learner 1:N Recommendation; LearningPath 1:N Recommendation; ContentItem 1:N Recommendation (optional for escalations)",
      [C("recommendation_id", "TEXT", uniq=True, rule="^REC-\\d{8}$ (chronological)"),
       C("learner_id", "TEXT", fk="Learner.learner_id"), C("path_id", "TEXT", fk="LearningPath.path_id"),
       C("content_id", "TEXT", False, fk="ContentItem.content_id", rule="null iff ESCALATED; all REQUIRED prerequisites met at recommended_at"),
       C("skill_id", "TEXT", False, fk="Skill.skill_id", rule="primary skill of content_id"),
       C("recommended_at", "TIMESTAMP"), C("rank", "INTEGER", rule="1..3 contiguous per decision"),
       C("score", "REAL", False, rule="ranking score (higher is better)"),
       C("reason_code", "TEXT", allowed=list(REASON_CODES)), C("rationale", "TEXT", rule="human-readable explanation, never empty"),
       C("mastery_snapshot", "REAL", False, unit="mastery 0..1", rule="primary-skill mastery at recommended_at"),
       C("target_difficulty", "INTEGER", False, allowed=[1, 2, 3, 4, 5], rule="1 + round(4 x mastery_snapshot)"),
       C("prereqs_checked", "INTEGER", rule="number of REQUIRED prerequisite rules evaluated"),
       C("model_version", "TEXT", allowed=["LP-RULES-1.0"]),
       C("status", "TEXT", allowed=REC_STATUSES, rule="derived: ACCEPTED if attempted within 14 days, EXPIRED after, else ISSUED"),
       C("outcome", "TEXT", allowed=REC_OUTCOMES, rule="derived from the first attempt on content_id within 14 days"),
       C("outcome_attempt_id", "TEXT", False, fk="Attempt.attempt_id"),
       C("outcome_score_pct", "REAL", False, unit="%", rule="= outcome attempt score_pct"),
       C("outcome_at", "TIMESTAMP", False, rule="= outcome attempt started_at")])

GROUND_TRUTH_COLUMNS = ["gt_id", "entity_type", "entity_id", "issue_type", "expected_detection_rule", "expected_decision", "context"]
LEAK_COLUMNS = {"issue_type", "ground_truth", "gt_id", "is_anomaly", "expected_decision", "injected", "true_mastery"}


def columns(tname):
    return [c[0] for c in SCHEMA[tname]["cols"]]


def by_file():
    return {v["file"]: k for k, v in SCHEMA.items()}
