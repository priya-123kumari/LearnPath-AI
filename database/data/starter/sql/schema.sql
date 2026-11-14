-- LearnPath AI database schema (SQLite). Auto-generated from database/generator/schema.py
PRAGMA foreign_keys = ON;

-- Learner: Learner master record. Progress lives in events (attempts, results, path events), never on this row.
CREATE TABLE learners (
  learner_id TEXT NOT NULL,
  display_name TEXT NOT NULL,
  email TEXT NOT NULL UNIQUE,
  country TEXT NOT NULL CHECK (country IN ('IN', 'US', 'GB', 'NG', 'BR', 'DE', 'PH', 'CA', 'KE', 'ID', 'MX', 'AU')),
  prior_level TEXT NOT NULL CHECK (prior_level IN ('NOVICE', 'INTERMEDIATE', 'ADVANCED')),
  cohort TEXT NOT NULL CHECK (cohort IN ('2026-Q1', '2026-Q2', '2026-Q3', '2026-Q4')),
  enrolled_at TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('ACTIVE', 'WITHDRAWN')),
  withdrawn_at TEXT,
  PRIMARY KEY (learner_id)
);

-- Course: Course (master data). 5 courses per domain in learning order; each owns 20 skills.
CREATE TABLE courses (
  course_id TEXT NOT NULL,
  course_code TEXT NOT NULL UNIQUE,
  title TEXT NOT NULL,
  domain TEXT NOT NULL,
  sequence_in_domain INTEGER NOT NULL,
  level TEXT NOT NULL CHECK (level IN ('INTRODUCTORY', 'INTERMEDIATE', 'ADVANCED')),
  credits INTEGER NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('ACTIVE', 'ARCHIVED')),
  effective_from TEXT NOT NULL,
  effective_to TEXT,
  PRIMARY KEY (course_id)
);

-- Skill: Skill node of the prerequisite graph. Each course covers 4 topics x 5 tiers.
CREATE TABLE skills (
  skill_id TEXT NOT NULL,
  course_id TEXT NOT NULL,
  skill_name TEXT NOT NULL UNIQUE,
  topic TEXT NOT NULL,
  tier INTEGER NOT NULL CHECK (tier IN (1, 2, 3, 4, 5)),
  status TEXT NOT NULL CHECK (status IN ('ACTIVE', 'DEPRECATED')),
  effective_from TEXT NOT NULL,
  PRIMARY KEY (skill_id),
  FOREIGN KEY (course_id) REFERENCES courses(course_id) DEFERRABLE INITIALLY DEFERRED
);

-- SkillPrerequisite: Directed, effective-dated edge of the skill graph: prerequisite_skill_id must reach min_mastery before skill_id is eligible.
CREATE TABLE skill_prerequisites (
  prerequisite_id TEXT NOT NULL,
  skill_id TEXT NOT NULL,
  prerequisite_skill_id TEXT NOT NULL,
  relation_type TEXT NOT NULL CHECK (relation_type IN ('REQUIRED', 'RECOMMENDED')),
  min_mastery REAL NOT NULL,
  cross_course INTEGER NOT NULL CHECK (cross_course IN (0,1)),
  effective_from TEXT NOT NULL,
  effective_to TEXT,
  PRIMARY KEY (prerequisite_id),
  FOREIGN KEY (skill_id) REFERENCES skills(skill_id) DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (prerequisite_skill_id) REFERENCES skills(skill_id) DEFERRABLE INITIALLY DEFERRED
);

-- ContentItem: Learning activity (video, reading, quiz, exercise, interactive lab, project).
CREATE TABLE content_items (
  content_id TEXT NOT NULL,
  course_id TEXT NOT NULL,
  title TEXT NOT NULL,
  format TEXT NOT NULL CHECK (format IN ('VIDEO', 'READING', 'QUIZ', 'EXERCISE', 'INTERACTIVE', 'PROJECT')),
  difficulty INTEGER NOT NULL CHECK (difficulty IN (1, 2, 3, 4, 5)),
  est_minutes INTEGER NOT NULL,
  is_assessed INTEGER NOT NULL CHECK (is_assessed IN (0,1)),
  max_score INTEGER,
  pass_threshold_pct REAL,
  status TEXT NOT NULL CHECK (status IN ('DRAFT', 'PUBLISHED', 'RETIRED')),
  published_at TEXT,
  retired_at TEXT,
  PRIMARY KEY (content_id),
  FOREIGN KEY (course_id) REFERENCES courses(course_id) DEFERRABLE INITIALLY DEFERRED
);

-- ContentSkill: Bridge table for the N:M relationship ContentItem <-> Skill.
CREATE TABLE content_skills (
  content_skill_id TEXT NOT NULL,
  content_id TEXT NOT NULL,
  skill_id TEXT NOT NULL,
  weight REAL NOT NULL,
  is_primary INTEGER NOT NULL CHECK (is_primary IN (0,1)),
  PRIMARY KEY (content_skill_id),
  FOREIGN KEY (content_id) REFERENCES content_items(content_id) DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (skill_id) REFERENCES skills(skill_id) DEFERRABLE INITIALLY DEFERRED
);

-- LearningPath: A learner's enrolment in one course. Status and progress are DERIVED from LearningPathEvent.
CREATE TABLE learning_paths (
  path_id TEXT NOT NULL,
  learner_id TEXT NOT NULL,
  course_id TEXT NOT NULL,
  created_at TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('ACTIVE', 'STALLED', 'COMPLETED', 'ABANDONED')),
  status_changed_at TEXT NOT NULL,
  skills_total INTEGER NOT NULL,
  skills_mastered INTEGER NOT NULL,
  progress_pct REAL NOT NULL,
  last_activity_at TEXT,
  completed_at TEXT,
  PRIMARY KEY (path_id),
  FOREIGN KEY (learner_id) REFERENCES learners(learner_id) DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (course_id) REFERENCES courses(course_id) DEFERRABLE INITIALLY DEFERRED
);

-- LearningPathEvent: Append-only path history: creation, every assigned step, each newly mastered skill and every status change.
CREATE TABLE learning_path_events (
  event_id TEXT NOT NULL,
  path_id TEXT NOT NULL,
  event_seq INTEGER NOT NULL,
  event_type TEXT NOT NULL CHECK (event_type IN ('PATH_CREATED', 'STEP_ASSIGNED', 'SKILL_MASTERED', 'STATUS_CHANGED')),
  event_at TEXT NOT NULL,
  from_status TEXT CHECK (from_status IN ('ACTIVE', 'STALLED', 'COMPLETED', 'ABANDONED')),
  to_status TEXT CHECK (to_status IN ('ACTIVE', 'STALLED', 'COMPLETED', 'ABANDONED')),
  content_id TEXT,
  skill_id TEXT,
  recommendation_id TEXT,
  mastery_snapshot REAL,
  PRIMARY KEY (event_id),
  FOREIGN KEY (path_id) REFERENCES learning_paths(path_id) DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (content_id) REFERENCES content_items(content_id) DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (skill_id) REFERENCES skills(skill_id) DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (recommendation_id) REFERENCES recommendations(recommendation_id) DEFERRABLE INITIALLY DEFERRED
);

-- Attempt: One learner attempt at one content item. Counter is chronological per learner.
CREATE TABLE attempts (
  attempt_id TEXT NOT NULL,
  learner_id TEXT NOT NULL,
  content_id TEXT NOT NULL,
  path_id TEXT NOT NULL,
  recommendation_id TEXT,
  attempt_no INTEGER NOT NULL,
  started_at TEXT NOT NULL,
  submitted_at TEXT,
  duration_sec INTEGER NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('COMPLETED', 'ABANDONED')),
  raw_score INTEGER,
  max_score INTEGER,
  score_pct REAL,
  passed INTEGER CHECK (passed IN (0,1)),
  completion_pct REAL NOT NULL,
  PRIMARY KEY (attempt_id),
  FOREIGN KEY (learner_id) REFERENCES learners(learner_id) DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (content_id) REFERENCES content_items(content_id) DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (path_id) REFERENCES learning_paths(path_id) DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (recommendation_id) REFERENCES recommendations(recommendation_id) DEFERRABLE INITIALLY DEFERRED
);

-- AssessmentResult: Append-only mastery evidence: one row per (assessed, completed attempt x mapped skill). Mastery is replayable from attempts.
CREATE TABLE assessment_results (
  result_id TEXT NOT NULL,
  attempt_id TEXT NOT NULL,
  learner_id TEXT NOT NULL,
  skill_id TEXT NOT NULL,
  content_id TEXT NOT NULL,
  evidence_weight REAL NOT NULL,
  score_pct REAL NOT NULL,
  mastery_before REAL NOT NULL,
  mastery_after REAL NOT NULL,
  evidence_count INTEGER NOT NULL,
  mastery_level TEXT NOT NULL CHECK (mastery_level IN ('NOT_STARTED', 'DEVELOPING', 'PROFICIENT', 'MASTERED')),
  computed_at TEXT NOT NULL,
  model_version TEXT NOT NULL CHECK (model_version IN ('EWMA-1.0')),
  PRIMARY KEY (result_id),
  FOREIGN KEY (attempt_id) REFERENCES attempts(attempt_id) DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (learner_id) REFERENCES learners(learner_id) DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (skill_id) REFERENCES skills(skill_id) DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (content_id) REFERENCES content_items(content_id) DEFERRABLE INITIALLY DEFERRED
);

-- Recommendation: Ranked next-activity recommendation with reason code, rationale and the outcome observed afterwards.
CREATE TABLE recommendations (
  recommendation_id TEXT NOT NULL,
  learner_id TEXT NOT NULL,
  path_id TEXT NOT NULL,
  content_id TEXT,
  skill_id TEXT,
  recommended_at TEXT NOT NULL,
  rank INTEGER NOT NULL,
  score REAL,
  reason_code TEXT NOT NULL CHECK (reason_code IN ('COLD_START_DIAGNOSTIC', 'PREREQ_GAP_FILL', 'REMEDIATE_LOW_MASTERY', 'NEXT_IN_SEQUENCE', 'CONTINUE_PRACTICE', 'STRETCH_CHALLENGE', 'SPACED_REVIEW', 'NO_ELIGIBLE_CONTENT')),
  rationale TEXT NOT NULL,
  mastery_snapshot REAL,
  target_difficulty INTEGER CHECK (target_difficulty IN (1, 2, 3, 4, 5)),
  prereqs_checked INTEGER NOT NULL,
  model_version TEXT NOT NULL CHECK (model_version IN ('LP-RULES-1.0')),
  status TEXT NOT NULL CHECK (status IN ('ISSUED', 'ACCEPTED', 'EXPIRED', 'ESCALATED')),
  outcome TEXT NOT NULL CHECK (outcome IN ('PENDING', 'NOT_ATTEMPTED', 'COMPLETED_PASS', 'COMPLETED_FAIL', 'COMPLETED_UNSCORED', 'ABANDONED', 'ESCALATED')),
  outcome_attempt_id TEXT,
  outcome_score_pct REAL,
  outcome_at TEXT,
  PRIMARY KEY (recommendation_id),
  FOREIGN KEY (learner_id) REFERENCES learners(learner_id) DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (path_id) REFERENCES learning_paths(path_id) DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (content_id) REFERENCES content_items(content_id) DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (skill_id) REFERENCES skills(skill_id) DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (outcome_attempt_id) REFERENCES attempts(attempt_id) DEFERRABLE INITIALLY DEFERRED
);

-- query indexes used by the backend
CREATE INDEX ix_attempts_learner ON attempts(learner_id, started_at);
CREATE INDEX ix_results_learner ON assessment_results(learner_id, skill_id);
CREATE INDEX ix_recs_learner ON recommendations(learner_id, recommended_at);
CREATE INDEX ix_events_path ON learning_path_events(path_id, event_seq);
CREATE INDEX ix_paths_learner ON learning_paths(learner_id);
CREATE INDEX ix_content_skills_content ON content_skills(content_id);
