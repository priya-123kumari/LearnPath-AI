# LearnPath AI: Next-Activity Recommendations (three-tier app + synthetic data)

LearnPath AI is a complete workflow that **recommends the next learning activity for each learner from their skills,
the prerequisites, their assessment results and the content difficulty**.

It runs end to end:

1. It builds a skill graph with effective-dated prerequisites and maps content to skills and difficulty.
2. It simulates learner attempts over time and derives a reproducible mastery estimate from them.
3. It recommends eligible items with reason codes, rationale and recorded outcomes.
4. It injects labelled edge cases and keeps them in a separate ground truth.
5. It validates everything, evaluates on a temporal split and proves fixed-seed reproducibility.

The same logic is served by a REST API and a React UI.

| Tier | Folder | Stack | Role |
|---|---|---|---|
| **Frontend** (presentation) | `frontend/` | React 18, Vite, Tailwind CSS, Lucide | Screens for learners, instructors, support staff, academic and platform administrators |
| **Backend** (application) | `backend/` | Python, FastAPI | Business rules (mastery and recommender engine), services, REST API. The only tier that touches the database |
| **Database** (data) | `database/` | SQLite, Python generator (`numpy`, `pandas`) | Schema, synthetic data generator, CSV/JSON/SQL datasets, database loader |

The tiers only talk in one direction: frontend → backend `/api` → database.

## Reviewer guide

| Question | Where |
|---|---|
| How do I run it? | **Quick start** below |
| Problem, assumptions, rules, trade-offs, testing, limitations | [`docs/DESIGN_DECISIONS.md`](docs/DESIGN_DECISIONS.md) |
| Data dictionary, ERD, schema | [`docs/data_dictionary.md`](docs/data_dictionary.md), [`docs/erd.md`](docs/erd.md), [`docs/schema.sql`](docs/schema.sql) |
| Validation result (full dataset) | [`validation_summary.json`](validation_summary.json) |
| Reproducibility result | [`reproducibility_report.json`](reproducibility_report.json) |
| Which AI was used, how, and what was verified | [`AI_USAGE.md`](AI_USAGE.md) and [`ai/prompt_history.md`](ai/prompt_history.md) |

## Quick start

You need Python 3.10+ and Node.js 18+. Run everything from the repo root. On Windows use `python`; on macOS/Linux use `python3`.

```bash
pip install -r requirements.txt

# 1. DATABASE tier: generate data (starter is already committed) and build the SQLite database
python -m database.generator --scale starter --out database/data/starter --docs docs     # ~20 s
python -m database.load_db --data database/data/starter --db database/learnpath.db

# 2. BACKEND tier: REST API on http://localhost:8000  (interactive docs: http://localhost:8000/docs)
python -m uvicorn backend.main:app --port 8000     # run from the repo root, NOT from inside backend/

# 3. FRONTEND tier: in a second terminal, open http://localhost:5173
cd frontend
npm install
npm run dev
```

Tests and reproducibility:

```bash
python -m pytest -q                       # 30 tests across the three tiers (python tests/run_without_pytest.py also works)
./reproducibility_check.sh                # or: python -m database.generator.reproduce --scale starter --against database/data/starter
```

**Full dataset:** 10,000 learners, 500 skills, 2,000 content items and 500,000 attempts. It is the same generator with a different scale:

```bash
python -m database.generator --seed 20261022 --learners 10000 --skills 500 --content 2000 --attempts 500000 --out database/data/full --no-big-json
python -m database.load_db --data database/data/full --db database/learnpath.db      # optional: serve the full data
```

It takes about 5 minutes. The CSV and SQL files (~700 MB) are not in Git. Their `checksums.json`, outputs, ground truth, manifest and schema
**are** committed. `python -m database.generator.reproduce --scale full --against database/data/full` proves a regenerated copy matches byte for byte.
The CLI exits with a non-zero code if validation fails.

## What the generator produces (`database/data/<scale>/`)

| Path | Content |
|---|---|
| `csv/`, `json/` | The 11 tables of the data model. Timestamps are ISO-8601 UTC (`...Z`) and booleans are `0/1` |
| `sql/schema.sql`, `sql/seed.sql` | DDL (PK, FK, CHECK, indexes) plus INSERT seed data. Loads into SQLite; `PRAGMA foreign_key_check` lists only the labelled anomaly rows |
| `ground_truth/ground_truth.csv/.json` | Every injected anomaly: entity, `issue_type`, detection rule and expected decision. **Never joined into input tables** |
| `ground_truth/true_mastery.csv` | Hidden true mastery per learner and skill (a label used only to score the mastery estimate) |
| `outputs/validation_summary.json` | All 228 validation checks (44 million rows examined for the full set) |
| `outputs/evaluation_metrics.json` | Detection precision/recall, temporal-split recommendation quality, mastery quality, outcomes by reason code, distributions |
| `outputs/exception_queue.csv` | Cases routed to a person, with the owner role and the recommended action |
| `manifest/source_manifest.json`, `checksums.json` | Provenance (no external data), generator command, seed, row counts, and a SHA-256 hash of every file |

## Data model (11 tables)

**Master data:**

* **Course** (25): 5 domains × 5 courses in learning order
* **Skill** (500): 4 topics × 5 tiers per course
* **SkillPrerequisite**: the N:M bridge Skill→Skill. It is effective-dated and acyclic: an edge points to a lower tier, or to tier 3 of the previous course
* **ContentItem** (2,000): 6 formats, difficulty 1–5, and a lifecycle of DRAFT → PUBLISHED → RETIRED
* **ContentSkill**: the N:M bridge ContentItem↔Skill, with exactly one primary skill per item

**Transactions and events:**

* **Learner** (10,000)
* **LearningPath**: one per learner and course. Status and progress are derived from events
* **LearningPathEvent**: append-only. Event types are PATH_CREATED, STEP_ASSIGNED, SKILL_MASTERED and STATUS_CHANGED
* **Attempt** (500,000)
* **AssessmentResult**: append-only mastery evidence, one row per assessed attempt and mapped skill
* **Recommendation**: rank, reason code, rationale and the outcome observed afterwards

**IDs:**

* `LRN-000001`, `CRS-000001`, `SKL-000001`, `CNT-000001`
* `ATT-<learner-id>-000001`, e.g. `ATT-LRN-000001-000001`. The counter is chronological per learner
* `PATH-2026-000001`
* `SPR-`, `CSK-`, `ASR-`, `PEV-` and `REC-` for the entities the brief leaves open

Counters are zero-padded and IDs are never reused. Every referenced ID is validated.

**Cardinality and optional relationships:**

* Learner 1:N LearningPath / Attempt / Recommendation; Attempt 1:N AssessmentResult; LearningPath 1:N LearningPathEvent
* Recommendation 0..1:N Attempt (`recommendation_id` is set when the learner followed it)
* Recommendation 0..1:1 STEP_ASSIGNED event
* `Recommendation.content_id` is null for escalations
* Other optional fields: `Learner.withdrawn_at`, `ContentItem.published_at/retired_at`, `SkillPrerequisite.effective_to` and `Attempt.submitted_at` (abandoned attempts)

## Business rules and why

1. **Mastery is replayable.** It is an EWMA of weighted evidence:
   `after = round(before + 0.40·w·(min(1, s·(0.8+0.05·difficulty)) − before), 4)`.
   Only attempts submitted at or before the as-of time count, so the estimate never uses future data. The backend recomputes it live and
   shows `REPRODUCIBLE` when the replay matches the stored value.
2. **Prerequisites gate eligibility.** Every REQUIRED rule in force on that date must be met (min mastery 0.6 or 0.7).
   Why: recommending locked content sets learners up to fail. The pass rate with a prerequisite gap is 14%, against 77% without one.
3. **Ranking matches the learner's level.** Target difficulty is `1 + round(4·mastery)`.
   Scoring favours low-mastery skills, a close difficulty fit, assessed items and lower tiers. It penalises repeats and failures.
4. **Every recommendation has a reason code and a rationale.** The codes are:
   * `COLD_START_DIAGNOSTIC`
   * `PREREQ_GAP_FILL`: walks back through earlier courses
   * `REMEDIATE_LOW_MASTERY`
   * `NEXT_IN_SEQUENCE`
   * `CONTINUE_PRACTICE`
   * `STRETCH_CHALLENGE`
   * `SPACED_REVIEW`
   * `NO_ELIGIBLE_CONTENT`: the exception path, escalated to an instructor
5. **The loop guard stops repetition.** An item assigned twice without a mastery gain of 0.02 is excluded.
6. **Outcomes come from rules.** The outcome is the first attempt on the item within 14 days. Path status comes from activity gaps
   (30 days → STALLED), mastery events (COMPLETED) and withdrawal (ABANDONED).
7. **History is append-only.** Recording an attempt through the API appends the attempt, its evidence and its path events.
   Only derived summary fields are refreshed.

## Injected edge cases (labelled in `ground_truth/`)

| issue_type | Injection | Detection rule | Full-data precision / recall |
|---|---|---|---|
| `RECOMMENDATION_VIOLATES_PREREQUISITE` (60) | unfollowed rank 2–3 recommendation re-pointed at a locked item | REQUIRED prerequisite mastery at `recommended_at` < `min_mastery` | 1.00 / 1.00 |
| `ATTEMPT_TIMESTAMP_ORDER_INVALID` (100) | `submitted_at < started_at`, or started before the previous attempt in counter order | either inequality, or `duration_sec` mismatch | 1.00 / 1.00 |
| `CONTENT_MAPPED_TO_NONEXISTENT_SKILL` (15) | ContentSkill row to an unknown `SKL-` id | FK check | 1.00 / 1.00 |
| `MASTERY_USES_FUTURE_ATTEMPT` (60) | `computed_at` stamped before its evidence was submitted | `computed_at < Attempt.submitted_at` | 1.00 / 1.00 |
| `LEARNER_PATH_LOOPS_WITHOUT_PROGRESS` (20) | 5 identical STEP_ASSIGNED steps with no attempt and no gain | ≥ 4 consecutive identical steps, gain < 0.02 | 1.00 / 1.00 |

Anomalies are rare (0.05% of attempts) and their targets are disjoint. Final IDs are assigned after injection, so an anomaly cannot be spotted
from its ID position.

## Validation (`database/generator/validate.py`)

There are 228 checks:

* PK uniqueness and non-null
* ID formats
* **FK integrity on every join**
* required fields, enums and conditional fields
* date ordering: enrolment → path → attempt; submitted ≥ started; counter order = time order; content published at attempt time; nothing after withdrawal; evidence not before its attempt
* skill graph: no self loops, edges point backwards, **acyclic**
* **arithmetic reconciliation:** duration, score %, passed, attempt numbering
* **full mastery replay** of every evidence row
* evidence completeness
* recommendation outcomes re-derived
* path summary and status events re-derived
* **legal lifecycle transitions**
* reason codes present
* contiguous ranks
* **prerequisites respected**
* no path loops
* duplicates
* ground-truth IDs exist
* **no ground-truth column in any input table**

A finding on a labelled anomaly, from its intended check, is *expected*. Any other finding is an *unexpected error*.
The status is `PASS` only when there are 0 unexpected errors and 0 missed labels. **Full dataset: PASS, 0 unexpected errors, all 355 labelled findings observed.**

## Evaluation (full dataset, temporal split at 2026-09-01)

State is rebuilt from attempts **before** the cutoff only. The engine recommends at the cutoff, and the next 30 days are the test set
(3,000 learners; 361,752 training and 68,420 test attempts).

| Metric | Engine | Popularity baseline |
|---|---|---|
| Recommended items with an unmet prerequisite | **0.0%** | 21.2% |
| Hit rate @3 (a recommended item was attempted) | 99.3% | 51.1% |
| Next attempt was a recommended item | 84.0% | 14.9% |
| Reason-code coverage | 100% | n/a |

* Mastery at the cutoff predicts passing in the test window with **AUC 0.84**. The pass rate is 48% for not-started skills, 72% developing, 98% proficient and 99.9% mastered.
* Estimated mastery correlates with the hidden true mastery at **r = 0.88** (MAE 0.11, 77,777 learner-skill pairs).
* Hit rate is partly self-fulfilling, because simulated learners follow recommendations 80% of the time. The prerequisite and mastery results are the independent evidence (see `docs/DESIGN_DECISIONS.md`).

**Coverage of the full dataset:**

* 800 cold-start learners
* 184 learners with 1–5 attempts
* 1,093 withdrawn learners
* 57% repeated attempts
* 6.3% prerequisite-gap attempts
* 4% abandoned attempts
* 6 content formats, plus drafts and retired items
* 150 learners on more than one path
* 2,936 stalled paths
* 129 natural escalations

## Using the app (frontend)

| Screen | Who it is for | What it shows |
|---|---|---|
| Overview | everyone | Validation verdict, engine vs baseline, the workflow, reason/outcome/status mixes, coverage, exception summary, table counts |
| Learner 360 | learner, instructor, support staff | Profile and paths; **live recommendations** with reason, rationale and "why are items locked"; **record an attempt** (validated, append-only); mastery with a reproducibility badge; recommendation history with outcomes; recent attempts |
| Skill graph | instructor, academic administrator | Prerequisite DAG per course, coloured by a learner's state (mastered / in progress / unlocked / locked); content-gap skills highlighted |
| Exception queue | instructor, support staff, admins | Escalations, remediation reviews (3 consecutive fails), content coverage gaps, stalled paths, data-quality findings |
| Data quality | platform administrator | Validation checks, detection vs ground truth, the ground-truth list |
| Evaluation | academic and platform administrators | Temporal split, engine vs baseline, mastery quality, outcomes by reason code |

Click any ID (`LRN-`, `REC-`, `ATT-`, `PATH-2026-`, ...) or use the search box to open its full record trail.

## API (backend)

`GET /api/health` · `GET /api/overview` · `GET /api/learners?q=&status=` · `GET /api/learners/{id}` ·
`GET /api/learners/{id}/mastery?as_of=` · `GET /api/learners/{id}/recommendations?as_of=&k=` (live, read-only) ·
`POST /api/learners/{id}/recommendations` (append) · `POST /api/attempts` (append) · `GET /api/courses` ·
`GET /api/courses/{id}/graph?learner_id=` · `GET /api/content` · `GET /api/records/{id}` · `GET /api/quality` ·
`GET /api/exceptions` · `GET /api/evaluation`.

Errors come back as `{"error": CODE, "message": ...}`. Examples:

* `ATTEMPT_TIMESTAMP_ORDER_INVALID` (409)
* `CONTENT_NOT_PUBLISHED` (409)
* `LEARNER_WITHDRAWN` (409)
* `INVALID_SCORE` (422)

## Reproducibility

* **Determinism.** The generator uses one `numpy.random.default_rng(20261022)`. A Python `random.Random` is seeded from it.
* **No hidden variation.** There is no wall-clock time and no unordered iteration, and rows are sorted by primary key before writing.
* **Check.** `reproducibility_check.sh` runs the generator twice into temp folders and compares per-table row counts and the SHA-256 of every output file.
  It also compares them with the committed dataset. The result is in `reproducibility_report.json`.
* **Parameters.** Changing `--seed` changes the data; `--scale` or the size flags rescale it.

## Provenance and lawful use

No external data is used (`manifest/source_manifest.json`: `external_data_used = false`). Names come from small synthetic lists,
and e-mails use the reserved `example.edu` domain. No personal or confidential information exists in the dataset.
Public learning-science ideas (prerequisite graphs, mastery learning, spaced review) were used for schema inspiration only.

## Repository layout

```
LearnPath AI/
├── frontend/                        # TIER 1 - presentation (React + Vite + Tailwind)
│   ├── src/
│   │   ├── App.jsx                  # Layout, navigation, record search
│   │   ├── api.js                   # The only data source: fetch('/api/...')
│   │   ├── Trace.jsx                # Record trail for any ID
│   │   ├── ui.jsx                   # Cards, tables, bars, pills, drawer
│   │   ├── styles.css               # Tailwind setup, colours, dark mode
│   │   ├── main.jsx
│   │   └── tabs/                    # Overview, Learners, SkillGraph, Exceptions, Quality, Evaluation
│   ├── index.html
│   ├── package.json
│   └── vite.config.js               # /api proxy -> backend
├── backend/                         # TIER 2 - application (FastAPI)
│   ├── config.py                    # Business-rule thresholds, reason codes
│   ├── engine.py                    # Mastery model + rule-based recommender
│   ├── service.py                   # Learner state, live recommendations, record attempt, trace, admin views
│   ├── db.py                        # The only module that opens the database
│   └── main.py                      # REST endpoints
├── database/                        # TIER 3 - data
│   ├── generator/                   # python -m database.generator
│   │   ├── config.py                # Seed, scales, rates, timeline
│   │   ├── reference.py             # Domains, topics, formats, name pools
│   │   ├── schema.py                # Table definitions (single source of truth)
│   │   ├── master_data.py           # Courses, skills, prerequisite graph, content
│   │   ├── simulate.py              # Learners, paths, attempts, evidence, recommendations
│   │   ├── derive.py                # Outcomes and path status from source records
│   │   ├── anomalies.py             # Labelled edge-case injection
│   │   ├── rules.py                 # Detection rules
│   │   ├── validate.py              # 228 validation checks
│   │   ├── evaluate.py              # Temporal split, baselines, metrics
│   │   ├── exceptions.py            # Exception queue
│   │   ├── export.py                # CSV, JSON, SQL, manifest, checksums
│   │   ├── docs.py                  # Writes docs/ from the schema
│   │   ├── reproduce.py             # Step 10 reproducibility check
│   │   ├── build.py                 # Runs the steps in order
│   │   └── __main__.py              # Command-line entry point
│   ├── data/
│   │   ├── starter/                 # 500 learners, 25,000 attempts (complete)
│   │   └── full/                    # 10,000 learners, 500,000 attempts (checksums, outputs, ground truth, manifest, schema)
│   └── load_db.py                   # Builds database/learnpath.db for the backend
├── docs/                            # DESIGN_DECISIONS.md, data_dictionary.md, erd.md, schema.sql
├── tests/                           # test_engine.py, test_pipeline.py, test_backend.py
├── ai/prompt_history.md
├── AI_USAGE.md
├── LICENSE
├── README.md
├── reproducibility_check.sh
├── reproducibility_report.json
├── requirements.txt
└── validation_summary.json
```

Generated or local files are ignored by Git, so they aren't listed:

* `frontend/node_modules/` and `frontend/dist/`
* `database/learnpath.db`
* the large full-scale CSV/JSON/SQL files
