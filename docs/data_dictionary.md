# Data dictionary

Generated from `database/generator/schema.py`. Every table has a single-column primary key; every relationship has a foreign key. Timestamps are UTC. `Req` = required (NOT NULL).

## Learner (`learners`)

Learner master record. Progress lives in events (attempts, results, path events), never on this row.

* **Primary key:** `learner_id`
* **Cardinality:** Learner 1:N LearningPath; Learner 1:N Attempt; Learner 1:N AssessmentResult; Learner 1:N Recommendation

| Field | Type | Req | Allowed values | Unit | Unique | Validation rule | FK |
|---|---|---|---|---|---|---|---|
| `learner_id` | text | yes |  |  | yes | ^LRN-\d{6}$ |  |
| `display_name` | text | yes |  |  |  | synthetic name, not a real person |  |
| `email` | text | yes |  |  | yes | learnerNNNNNN@example.edu (reserved domain) |  |
| `country` | text | yes | IN, US, GB, NG, BR, DE, PH, CA, KE, ID, MX, AU |  |  | ISO-3166 alpha-2 |  |
| `prior_level` | text | yes | NOVICE, INTERMEDIATE, ADVANCED |  |  | self-reported at enrolment; sets the starting course |  |
| `cohort` | text | yes | 2026-Q1, 2026-Q2, 2026-Q3, 2026-Q4 |  |  | = quarter of enrolled_at |  |
| `enrolled_at` | timestamp (ISO-8601 UTC, ...Z) | yes |  |  |  | 2026-01-05 .. AS_OF |  |
| `status` | text | yes | ACTIVE, WITHDRAWN |  |  |  |  |
| `withdrawn_at` | timestamp (ISO-8601 UTC, ...Z) | no |  |  |  | set iff WITHDRAWN; > last attempt; <= AS_OF |  |

## Course (`courses`)

Course (master data). 5 courses per domain in learning order; each owns 20 skills.

* **Primary key:** `course_id`
* **Cardinality:** Course 1:N Skill; Course 1:N ContentItem; Course 1:N LearningPath

| Field | Type | Req | Allowed values | Unit | Unique | Validation rule | FK |
|---|---|---|---|---|---|---|---|
| `course_id` | text | yes |  |  | yes | ^CRS-\d{6}$ |  |
| `course_code` | text | yes |  |  | yes | <domain prefix>-<seq>01, e.g. DS-301 |  |
| `title` | text | yes |  |  |  |  |  |
| `domain` | text | yes |  |  |  |  |  |
| `sequence_in_domain` | integer | yes |  |  |  | 1..5; course n builds on course n-1 |  |
| `level` | text | yes | INTRODUCTORY, INTERMEDIATE, ADVANCED |  |  |  |  |
| `credits` | integer | yes |  | credits |  | 2..6 |  |
| `status` | text | yes | ACTIVE, ARCHIVED |  |  |  |  |
| `effective_from` | date (YYYY-MM-DD) | yes |  |  |  |  |  |
| `effective_to` | date (YYYY-MM-DD) | no |  |  |  | >= effective_from |  |

## Skill (`skills`)

Skill node of the prerequisite graph. Each course covers 4 topics x 5 tiers.

* **Primary key:** `skill_id`
* **Cardinality:** Course 1:N Skill; Skill N:M Skill via SkillPrerequisite; Skill N:M ContentItem via ContentSkill

| Field | Type | Req | Allowed values | Unit | Unique | Validation rule | FK |
|---|---|---|---|---|---|---|---|
| `skill_id` | text | yes |  |  | yes | ^SKL-\d{6}$ |  |
| `course_id` | text | yes |  |  |  |  | Course.course_id |
| `skill_name` | text | yes |  |  | yes | <tier label> <topic> |  |
| `topic` | text | yes |  |  |  |  |  |
| `tier` | integer | yes | 1, 2, 3, 4, 5 |  |  | 1 = foundations .. 5 = expert |  |
| `status` | text | yes | ACTIVE, DEPRECATED |  |  |  |  |
| `effective_from` | date (YYYY-MM-DD) | yes |  |  |  |  |  |

## SkillPrerequisite (`skill_prerequisites`)

Directed, effective-dated edge of the skill graph: prerequisite_skill_id must reach min_mastery before skill_id is eligible.

* **Primary key:** `prerequisite_id`
* **Cardinality:** Skill N:M Skill (bridge). Graph must be acyclic.

| Field | Type | Req | Allowed values | Unit | Unique | Validation rule | FK |
|---|---|---|---|---|---|---|---|
| `prerequisite_id` | text | yes |  |  | yes | ^SPR-\d{6}$ |  |
| `skill_id` | text | yes |  |  |  |  | Skill.skill_id |
| `prerequisite_skill_id` | text | yes |  |  |  | != skill_id; lower tier in same course, or tier 3 of the previous course | Skill.skill_id |
| `relation_type` | text | yes | REQUIRED, RECOMMENDED |  |  | only REQUIRED rules gate eligibility |  |
| `min_mastery` | decimal | yes |  | mastery 0..1 |  | 0.6 or 0.7 |  |
| `cross_course` | boolean (0/1) | yes |  |  |  | 1 iff the two skills belong to different courses |  |
| `effective_from` | date (YYYY-MM-DD) | yes |  |  |  |  |  |
| `effective_to` | date (YYYY-MM-DD) | no |  |  |  | >= effective_from; null = still in force |  |

## ContentItem (`content_items`)

Learning activity (video, reading, quiz, exercise, interactive lab, project).

* **Primary key:** `content_id`
* **Cardinality:** Course 1:N ContentItem; ContentItem N:M Skill via ContentSkill; ContentItem 1:N Attempt

| Field | Type | Req | Allowed values | Unit | Unique | Validation rule | FK |
|---|---|---|---|---|---|---|---|
| `content_id` | text | yes |  |  | yes | ^CNT-\d{6}$ |  |
| `course_id` | text | yes |  |  |  |  | Course.course_id |
| `title` | text | yes |  |  |  |  |  |
| `format` | text | yes | VIDEO, READING, QUIZ, EXERCISE, INTERACTIVE, PROJECT |  |  |  |  |
| `difficulty` | integer | yes | 1, 2, 3, 4, 5 |  |  | ~ tier of primary skill +/- 1 |  |
| `est_minutes` | integer | yes |  | minutes |  | > 0 |  |
| `is_assessed` | boolean (0/1) | yes |  |  |  | 1 iff format in QUIZ, EXERCISE, INTERACTIVE, PROJECT |  |
| `max_score` | integer | no |  | points |  | set iff is_assessed |  |
| `pass_threshold_pct` | decimal | no |  | % |  | 70 iff is_assessed |  |
| `status` | text | yes | DRAFT, PUBLISHED, RETIRED |  |  |  |  |
| `published_at` | timestamp (ISO-8601 UTC, ...Z) | no |  |  |  | null iff DRAFT |  |
| `retired_at` | timestamp (ISO-8601 UTC, ...Z) | no |  |  |  | set iff RETIRED; > published_at |  |

## ContentSkill (`content_skills`)

Bridge table for the N:M relationship ContentItem <-> Skill.

* **Primary key:** `content_skill_id`
* **Cardinality:** ContentItem N:M Skill (each item has exactly one primary skill)

| Field | Type | Req | Allowed values | Unit | Unique | Validation rule | FK |
|---|---|---|---|---|---|---|---|
| `content_skill_id` | text | yes |  |  | yes | ^CSK-\d{6}$ |  |
| `content_id` | text | yes |  |  |  |  | ContentItem.content_id |
| `skill_id` | text | yes |  |  |  | skill of the same course | Skill.skill_id |
| `weight` | decimal | yes |  |  |  | 1.0 primary, 0.5 secondary |  |
| `is_primary` | boolean (0/1) | yes |  |  |  | exactly one primary per content item |  |

## LearningPath (`learning_paths`)

A learner's enrolment in one course. Status and progress are DERIVED from LearningPathEvent.

* **Primary key:** `path_id`
* **Cardinality:** Learner 1:N LearningPath; Course 1:N LearningPath; LearningPath 1:N LearningPathEvent / Attempt / Recommendation

| Field | Type | Req | Allowed values | Unit | Unique | Validation rule | FK |
|---|---|---|---|---|---|---|---|
| `path_id` | text | yes |  |  | yes | ^PATH-2026-\d{6}$ |  |
| `learner_id` | text | yes |  |  |  |  | Learner.learner_id |
| `course_id` | text | yes |  |  |  | unique per learner | Course.course_id |
| `created_at` | timestamp (ISO-8601 UTC, ...Z) | yes |  |  |  | >= Learner.enrolled_at |  |
| `status` | text | yes | ACTIVE, STALLED, COMPLETED, ABANDONED |  |  | = to_status of last STATUS event |  |
| `status_changed_at` | timestamp (ISO-8601 UTC, ...Z) | yes |  |  |  | = event_at of last STATUS event |  |
| `skills_total` | integer | yes |  |  |  | = skills in course |  |
| `skills_mastered` | integer | yes |  |  |  | = count of SKILL_MASTERED events |  |
| `progress_pct` | decimal | yes |  | % |  | = round(100 * skills_mastered / skills_total, 1) |  |
| `last_activity_at` | timestamp (ISO-8601 UTC, ...Z) | no |  |  |  | = max(started_at) of the path's attempts |  |
| `completed_at` | timestamp (ISO-8601 UTC, ...Z) | no |  |  |  | set iff COMPLETED |  |

## LearningPathEvent (`learning_path_events`)

Append-only path history: creation, every assigned step, each newly mastered skill and every status change.

* **Primary key:** `event_id`
* **Cardinality:** LearningPath 1:N LearningPathEvent; Recommendation 0..1:1 STEP_ASSIGNED event

| Field | Type | Req | Allowed values | Unit | Unique | Validation rule | FK |
|---|---|---|---|---|---|---|---|
| `event_id` | text | yes |  |  | yes | ^PEV-\d{8}$ |  |
| `path_id` | text | yes |  |  |  |  | LearningPath.path_id |
| `event_seq` | integer | yes |  |  |  | 1..n contiguous per path, ordered by event_at |  |
| `event_type` | text | yes | PATH_CREATED, STEP_ASSIGNED, SKILL_MASTERED, STATUS_CHANGED |  |  |  |  |
| `event_at` | timestamp (ISO-8601 UTC, ...Z) | yes |  |  |  | non-decreasing per path |  |
| `from_status` | text | no | ACTIVE, STALLED, COMPLETED, ABANDONED |  |  | STATUS_CHANGED only |  |
| `to_status` | text | no | ACTIVE, STALLED, COMPLETED, ABANDONED |  |  | PATH_CREATED / STATUS_CHANGED; legal transition |  |
| `content_id` | text | no |  |  |  | STEP_ASSIGNED only | ContentItem.content_id |
| `skill_id` | text | no |  |  |  | STEP_ASSIGNED / SKILL_MASTERED | Skill.skill_id |
| `recommendation_id` | text | no |  |  |  | STEP_ASSIGNED: rank-1 recommendation | Recommendation.recommendation_id |
| `mastery_snapshot` | decimal | no |  | mastery 0..1 |  | skill mastery when the event happened |  |

## Attempt (`attempts`)

One learner attempt at one content item. Counter is chronological per learner.

* **Primary key:** `attempt_id`
* **Cardinality:** Learner 1:N Attempt; ContentItem 1:N Attempt; LearningPath 1:N Attempt; Recommendation 0..1:N Attempt; Attempt 1:N AssessmentResult

| Field | Type | Req | Allowed values | Unit | Unique | Validation rule | FK |
|---|---|---|---|---|---|---|---|
| `attempt_id` | text | yes |  |  | yes | ^ATT-LRN-\d{6}-\d{6}$ i.e. ATT-<learner-id>-<seq>; seq order = started_at order |  |
| `learner_id` | text | yes |  |  |  | = learner in attempt_id | Learner.learner_id |
| `content_id` | text | yes |  |  |  | published at started_at | ContentItem.content_id |
| `path_id` | text | yes |  |  |  | path of the same learner | LearningPath.path_id |
| `recommendation_id` | text | no |  |  |  | set when the learner followed a recommendation | Recommendation.recommendation_id |
| `attempt_no` | integer | yes |  |  |  | 1..n contiguous per learner + content (repeated attempts) |  |
| `started_at` | timestamp (ISO-8601 UTC, ...Z) | yes |  |  |  | >= enrolled_at; <= AS_OF |  |
| `submitted_at` | timestamp (ISO-8601 UTC, ...Z) | no |  |  |  | null iff ABANDONED; >= started_at |  |
| `duration_sec` | integer | yes |  | seconds |  | = submitted_at - started_at (abandoned: time until leaving) |  |
| `status` | text | yes | COMPLETED, ABANDONED |  |  |  |  |
| `raw_score` | integer | no |  | points |  | set iff COMPLETED and assessed; 0..max_score |  |
| `max_score` | integer | no |  | points |  | = ContentItem.max_score |  |
| `score_pct` | decimal | no |  | % |  | = round(100 * raw_score / max_score, 2) |  |
| `passed` | boolean (0/1) | no |  |  |  | = score_pct >= pass_threshold_pct |  |
| `completion_pct` | decimal | yes |  | % |  | 100 if COMPLETED, else 5..90 |  |

## AssessmentResult (`assessment_results`)

Append-only mastery evidence: one row per (assessed, completed attempt x mapped skill). Mastery is replayable from attempts.

* **Primary key:** `result_id`
* **Cardinality:** Attempt 1:N AssessmentResult; Skill 1:N AssessmentResult

| Field | Type | Req | Allowed values | Unit | Unique | Validation rule | FK |
|---|---|---|---|---|---|---|---|
| `result_id` | text | yes |  |  | yes | ^ASR-\d{8}$ |  |
| `attempt_id` | text | yes |  |  |  |  | Attempt.attempt_id |
| `learner_id` | text | yes |  |  |  |  | Learner.learner_id |
| `skill_id` | text | yes |  |  |  |  | Skill.skill_id |
| `content_id` | text | yes |  |  |  |  | ContentItem.content_id |
| `evidence_weight` | decimal | yes |  |  |  | ContentSkill.weight x format weight (QUIZ .70, EXERCISE .85, INTERACTIVE .60, PROJECT 1.0) |  |
| `score_pct` | decimal | yes |  | % |  | = Attempt.score_pct |  |
| `mastery_before` | decimal | yes |  | mastery 0..1 |  | = previous mastery_after for learner+skill, 0 for first |  |
| `mastery_after` | decimal | yes |  | mastery 0..1 |  | round(before + 0.40*w*(min(1, s*(0.8+0.05*difficulty)) - before), 4), s = score_pct/100 |  |
| `evidence_count` | integer | yes |  |  |  | 1..n per learner+skill |  |
| `mastery_level` | text | yes | NOT_STARTED, DEVELOPING, PROFICIENT, MASTERED |  |  | DEVELOPING <0.5 <= PROFICIENT < 0.8 <= MASTERED |  |
| `computed_at` | timestamp (ISO-8601 UTC, ...Z) | yes |  |  |  | >= Attempt.submitted_at (must not use future evidence) |  |
| `model_version` | text | yes | EWMA-1.0 |  |  |  |  |

## Recommendation (`recommendations`)

Ranked next-activity recommendation with reason code, rationale and the outcome observed afterwards.

* **Primary key:** `recommendation_id`
* **Cardinality:** Learner 1:N Recommendation; LearningPath 1:N Recommendation; ContentItem 1:N Recommendation (optional for escalations)

| Field | Type | Req | Allowed values | Unit | Unique | Validation rule | FK |
|---|---|---|---|---|---|---|---|
| `recommendation_id` | text | yes |  |  | yes | ^REC-\d{8}$ (chronological) |  |
| `learner_id` | text | yes |  |  |  |  | Learner.learner_id |
| `path_id` | text | yes |  |  |  |  | LearningPath.path_id |
| `content_id` | text | no |  |  |  | null iff ESCALATED; all REQUIRED prerequisites met at recommended_at | ContentItem.content_id |
| `skill_id` | text | no |  |  |  | primary skill of content_id | Skill.skill_id |
| `recommended_at` | timestamp (ISO-8601 UTC, ...Z) | yes |  |  |  |  |  |
| `rank` | integer | yes |  |  |  | 1..3 contiguous per decision |  |
| `score` | decimal | no |  |  |  | ranking score (higher is better) |  |
| `reason_code` | text | yes | COLD_START_DIAGNOSTIC, PREREQ_GAP_FILL, REMEDIATE_LOW_MASTERY, NEXT_IN_SEQUENCE, CONTIN... |  |  |  |  |
| `rationale` | text | yes |  |  |  | human-readable explanation, never empty |  |
| `mastery_snapshot` | decimal | no |  | mastery 0..1 |  | primary-skill mastery at recommended_at |  |
| `target_difficulty` | integer | no | 1, 2, 3, 4, 5 |  |  | 1 + round(4 x mastery_snapshot) |  |
| `prereqs_checked` | integer | yes |  |  |  | number of REQUIRED prerequisite rules evaluated |  |
| `model_version` | text | yes | LP-RULES-1.0 |  |  |  |  |
| `status` | text | yes | ISSUED, ACCEPTED, EXPIRED, ESCALATED |  |  | derived: ACCEPTED if attempted within 14 days, EXPIRED after, else ISSUED |  |
| `outcome` | text | yes | PENDING, NOT_ATTEMPTED, COMPLETED_PASS, COMPLETED_FAIL, COMPLETED_UNSCORED, ABANDONED, ... |  |  | derived from the first attempt on content_id within 14 days |  |
| `outcome_attempt_id` | text | no |  |  |  |  | Attempt.attempt_id |
| `outcome_score_pct` | decimal | no |  | % |  | = outcome attempt score_pct |  |
| `outcome_at` | timestamp (ISO-8601 UTC, ...Z) | no |  |  |  | = outcome attempt started_at |  |
