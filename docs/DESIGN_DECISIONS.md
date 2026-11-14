# Design decisions

## 1. Problem

Recommend the next learning activity for each learner from four signals: **skills**, **prerequisites**,
**assessment results** and **content difficulty**. The workflow must show its key decisions and exceptions,
keep every step traceable, and produce outputs that can be measured.

## 2. Three-tier architecture

| Tier | Folder | Responsibility | Talks to |
|---|---|---|---|
| Presentation | `frontend/` | React UI for learners, instructors, support staff and administrators | backend only, over HTTP `/api` |
| Application | `backend/` | Business rules (`config.py`, `engine.py`), application services (`service.py`), REST API (`main.py`), data access (`db.py`) | database only |
| Data | `database/` | Schema, synthetic data generator, generated datasets, SQLite loader (`load_db.py`) | n/a |

* **Rules belong to the backend.** The database-tier generator imports `backend.engine` to simulate learners who follow
  recommendations. The synthetic history is therefore produced by exactly the rules the API serves. It is not a second copy that could drift.
* **Only `backend/db.py` opens the database at runtime.** The frontend never reads files. The Vite proxy forwards `/api` to FastAPI.
* **Audit material lives in separate `audit_*` tables:** ground truth, validation summary, metrics and the exception queue.
  The engine never queries them, so a label cannot leak into a decision.

## 3. Assumptions

* **Fully synthetic data.** There are 5 domains × 5 courses, and each course has 4 topics × 5 tiers = 20 skills.
  Courses in a domain build on each other: the tier-1 skills of course *n* need tier-3 of course *n-1*.
* **Fixed timeline.** Enrolments run from 2026-01-05 to the dataset "today" (`AS_OF` = 2026-10-31T23:59:59Z).
  Nothing calls the wall clock, so the same seed gives the same bytes.
* **Hidden learner state.** Each learner has a hidden ability, a hidden learning rate and a true mastery per skill.
  Scores are drawn from true mastery, item difficulty and true prerequisite gaps. The recommender sees **only** observed scores.
  True mastery is exported only as a label (`ground_truth/true_mastery.csv`).
* **Learner behaviour.** A learner follows the next recommended item 80% of the time and retries a failed item 55% of the time (at most 3 fails).
  Otherwise the learner browses. Locked-looking content is chosen only occasionally, which creates realistic prerequisite gaps of about 6% of attempts.
* **Content cut for revision.** In each course, one tier-2 skill loses all its content from August.
  This creates a real content-coverage gap that the academic administrator has to fix.

## 4. Business rules

1. **Mastery (EWMA-1.0).** For each assessed, completed attempt and each mapped skill:
   `after = round(before + 0.40 × w × (min(1, s × (0.8 + 0.05 × difficulty)) − before), 4)`,
   where `w` = ContentSkill weight × format weight (quiz .70, exercise .85, interactive .60, project 1.0).
   Videos and readings produce no evidence. Rounding at each step makes replays bit-exact.
   Levels: DEVELOPING < 0.5 ≤ PROFICIENT < 0.8 ≤ MASTERED.
2. **Eligibility.** A published item is eligible only if every **REQUIRED** prerequisite rule that is **in force on that date**
   (`effective_from ≤ t ≤ effective_to`) is met by the learner's current mastery. RECOMMENDED rules are shown but do not gate.
3. **Exclusions:**
   * `NOT_PUBLISHED`: draft, not yet released, or retired.
   * `PREREQ_NOT_MET`
   * `ALREADY_MASTERED`: unless it qualifies for spaced review or a stretch challenge.
   * `ALREADY_PASSED`: only once the skill is ≥ 0.70, the highest unlock threshold. Below that the item stays available,
     which removes a deadlock found during testing.
   * `LOOP_GUARD`: the same item assigned twice without a 0.02 mastery gain.
4. **Reason codes.** Each recommendation gets one reason code:
   * `COLD_START_DIAGNOSTIC`: no evidence yet. The easiest assessed items are recommended.
   * `PREREQ_GAP_FILL`: the engine walks back through unmet prerequisites in earlier courses until it finds eligible content.
   * `REMEDIATE_LOW_MASTERY`: at least 2 evidence rows and mastery below 0.4. Easier items are preferred.
   * `NEXT_IN_SEQUENCE`
   * `CONTINUE_PRACTICE`
   * `STRETCH_CHALLENGE`
   * `SPACED_REVIEW`: a mastered skill not practised for 21 days.
   * `NO_ELIGIBLE_CONTENT`: the exception path. The case is escalated to an instructor.
5. **Ranking.** `0.45(1−m) + 0.30·difficulty fit + 0.10·assessed + 0.10·lower tier first − fail and repeat penalties`.
   The engine returns the top 3, with at most 2 items per skill, and stores a human-readable rationale.
6. **Outcome (derived).** The outcome comes from the first attempt on the item within 14 days:
   `COMPLETED_PASS`, `COMPLETED_FAIL`, `COMPLETED_UNSCORED` or `ABANDONED`.
   A recommendation with no attempt becomes `NOT_ATTEMPTED`/`EXPIRED` once its window closes, or `PENDING`/`ISSUED` while it is open.
7. **Path lifecycle (derived from events).** Transitions are `ACTIVE ↔ STALLED → ABANDONED` and `ACTIVE → COMPLETED`:
   * STALLED after 30 days without an attempt
   * COMPLETED when every course skill has a SKILL_MASTERED event
   * ABANDONED when the learner withdraws

   Every change is a new LearningPathEvent. The path row only caches the result.
8. **Append-only history.** Attempts, assessment results, recommendations and path events are never updated in place.
   Only the derived summary fields are refreshed, by the rules above: recommendation outcome, and path status and progress.

## 5. Edge cases and how they are kept honest

All five are injected **after** the valid baseline is built. Each changes only its own target rows, and the targets are disjoint.
Each gets a ground-truth row with the detection rule and the expected decision.

| Issue | Injection | Detection rule | Decision |
|---|---|---|---|
| Recommendation violates prerequisite | a rank 2–3, never-followed recommendation is re-pointed at a locked item of the same course | REQUIRED prerequisite mastery at `recommended_at` < `min_mastery` (point-in-time `merge_asof`) | BLOCK_RECOMMENDATION |
| Attempt timestamp order invalid | half: `submitted_at < started_at`; half: started before the previous attempt in counter order (unscored items with no recommendation link, so nothing else changes) | either inequality, or `duration_sec` ≠ difference | QUARANTINE_ATTEMPT |
| Content mapped to nonexistent skill | extra ContentSkill row to an unused `SKL-` id | FK check (`PRAGMA foreign_key_check` lists exactly these rows) | REJECT_MAPPING |
| Mastery uses future attempt | `computed_at` stamped 1 h–10 days before the evidence was submitted | `computed_at < Attempt.submitted_at` | RECOMPUTE_MASTERY |
| Learner path loops without progress | 5 consecutive STEP_ASSIGNED events and recommendations of one item with no attempt and no gain (loop guard bypassed) | ≥ 4 consecutive identical steps whose mastery moves < 0.02 | ESCALATE_TO_INSTRUCTOR |

Final IDs are assigned **after** injection: REC ids in chronological order, PEV ids in path order, CSK ids by content.
Injected rows therefore cannot be spotted by their ID position.

## 6. Trade-offs

* **Rules engine, not an ML model.** The brief stresses decisions, exceptions and traceability. Every recommendation can be explained
  from its reason code and rationale, and replayed from attempts.
* **Simulation instead of independent random draws.** Generation is slower, about 1 minute for 500,000 attempts.
  In return, outcomes, mastery and statuses follow from documented rules, which is the brief's requirement for labels.
* **SQLite.** The data tier needs no server. `schema.sql` uses plain SQL with PK, FK and CHECK constraints, so it ports to PostgreSQL.
* **Full dataset not committed.** At about 700 MB it is too large for Git. Its `checksums.json`, outputs, ground truth, manifest and schema
  are committed. `python -m database.generator.reproduce --scale full --against database/data/full` regenerates it and proves it byte for byte.

## 7. Testing

* **Approach.** 30 tests in `tests/`, covering all three tiers. `python tests/run_without_pytest.py` works without pytest.
* **Engine (unit):**
  * known EWMA values
  * cold start is never recommended a locked item
  * a skill unlocks after mastery
  * effective-dated rules
  * loop guard
  * escalation
  * replay ignores future and abandoned attempts
* **Pipeline:**
  * ID formats and exact volumes
  * same seed gives identical frames and identical checksums
  * validation passes on good data and **fails** on 9 kinds of deliberate breakage
  * every anomaly is detected with precision and recall of 1.0
  * no leakage
  * prerequisite violations equal exactly the labelled set
  * mastery is reproducible for every learner
  * the temporal split holds
  * reason codes are present
  * coverage of cold start, repeats, gaps and formats
  * SQL seed loads and `foreign_key_check` lists only labelled rows
* **Backend (API):**
  * database built by the data tier
  * live mastery is reproducible
  * recommendations carry reasons
  * recording an attempt appends rows and raises mastery
  * structured errors for invalid timestamps, unknown content, unknown learner and unknown ID
  * persisting recommendations adds a STEP_ASSIGNED event
  * graph, quality, exceptions and evaluation endpoints

## 8. Evaluation

* **Temporal split.** All state is rebuilt from attempts that **started before 2026-09-01**, including the loop-guard history.
  The engine recommends at the cutoff. Attempts from 2026-09-01 to 2026-10-01 are the test set.
* **Baseline.** Popularity: the most-attempted items of the learner's courses in the training period.
* **Caveat.** Simulated learners follow recommendations 80% of the time, so hit rate is partly self-fulfilling.
  The independent evidence is that the baseline recommends locked items about 20% of the time while the engine recommends none.
  Further evidence is that pass rates in the test window rise steeply with mastery at the cutoff, and that estimated mastery tracks the hidden true mastery.

## 9. Limitations and next steps

* The learner model is simple: no forgetting curve and one ability per learner. The EWMA does not model guessing or slipping;
  Bayesian Knowledge Tracing would be the natural next step.
* Prerequisite thresholds are global (0.6/0.7). Per-skill calibration from outcome data is future work.
* The API has no authentication. The UI shows which actor each screen is for, but roles are not enforced.
* Live writes go to the SQLite file. Re-run `python -m database.load_db` to reset to the published dataset.
