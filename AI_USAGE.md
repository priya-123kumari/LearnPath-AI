### 1. Purpose

This file explains how AI tools were used to build LearnPath AI, what was checked, and what the author should be able to explain.

**AI tools used:**

- Claude Code (Anthropic), in VS Code: planning, all first-version code (generator, backend, frontend, tests), docs and the verification runs listed below.

Prompts: [`ai/prompt_history.md`](ai/prompt_history.md).

### 2. Where AI Helped

- Turning the problem statement into a three-tier plan (frontend / backend / database) following the structure of the earlier Pay Equity Audit Lab.
- The data model: 11 entities, keys, cardinality, effective dates, lifecycle states, ID conventions.
- Business logic in `backend/engine.py`: EWMA mastery, prerequisite eligibility, reason codes, loop guard, escalation.
- The synthetic data generator: a simulation driven by the backend engine, labelled edge cases, derived values, validation, evaluation, export.
- The FastAPI backend, the React + Tailwind frontend and the 30 tests.

### 3. Problems found and fixed during the build (from the session's own test runs)

- **Recommendation deadlock.** A skill between 0.5 and 0.7 mastery could not be practised (its items counted as "passed"), yet it was not strong enough to unlock the next skills. Fix: passed items stay eligible below 0.70 (`UNLOCK_AT`).
- **Unrealistic prerequisite-gap rate (30%).** Off-path learners only browsed their locked course. Fix: browse the courses the engine points to, and choose locked items only occasionally (now about 6%).
- **Loop detector recall 0.9 at full scale.** The rule judged a whole run of identical steps instead of any 4-step window. Fixed; recall is now 1.0.
- **Validator crashed on a deliberately duplicated primary key, and on a mixed-type comparison.** Both made robust; the negative tests now pass.

### 4. What was verified (commands run in the session)

- `python -m pytest -q` → **30 passed**.
- Full dataset (10,000 learners, 500,000 attempts): `validation=PASS`, 228 checks, 0 unexpected errors, every injected anomaly detected (precision and recall 1.0).
- Same-seed reproducibility check: see `reproducibility_report.json`.
- The UI was opened through the running backend and checked screen by screen.

### 5. Author's own review (to be completed by the author)

> _Add what you ran yourself on your own machine, what you changed, and what you checked by hand._

### 6. What the author should be able to explain

- Why the generator calls the backend engine (one set of rules, no drift between the data and the API).
- The EWMA mastery formula, and why each step is rounded (bit-exact replay).
- How eligibility uses effective-dated REQUIRED prerequisites.
- How each reason code is chosen, and the exception path (`NO_ELIGIBLE_CONTENT`, the exception queue).
- Why ground truth sits in separate files and `audit_*` tables, and how each label comes from a rule.
- The temporal split, and why the hit-rate result is partly self-fulfilling.
- How reproducibility is achieved: one seeded RNG, no wall clock, sorted output, IDs assigned after injection.

See [`docs/DESIGN_DECISIONS.md`](docs/DESIGN_DECISIONS.md) for assumptions, trade-offs, testing and limitations.
