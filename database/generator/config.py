"""Generator run configuration. Every knob lives here so starter and full datasets share one generator.
Business-rule thresholds are imported from the backend tier (backend/config.py)."""
from dataclasses import dataclass
import math
from backend.config import ts, iso, parse_iso, DAY, AS_OF, PASS_PCT, MODEL_VERSION, MASTERY_MODEL, OUTCOME_WINDOW_DAYS, STALL_AFTER_DAYS  # noqa: F401

SEED = 20261022
CATALOG_START = ts(2025, 12, 1)       # skills, prerequisites and first content published
TIMELINE_START = ts(2026, 1, 5)       # first learner enrolment
TEMPORAL_CUTOFF = ts(2026, 9, 1)      # evaluation: train = before cutoff, test = cutoff .. cutoff + 30 days
TEST_WINDOW_DAYS = 30
PREREQ_REVISION = ts(2026, 6, 30)     # a few prerequisite rules end on this date (effective-dated)
SKILLS_PER_COURSE = 20                # 4 topics x 5 tiers
TOPICS_PER_COURSE = 4
TIERS = 5
COURSES_PER_DOMAIN = 5
MAX_PATHS = 3

SCALES = {
    "tiny": dict(learners=80, skills=40, content=160, attempts=3_000),
    "starter": dict(learners=500, skills=100, content=400, attempts=25_000),
    "full": dict(learners=10_000, skills=500, content=2_000, attempts=500_000),
}


@dataclass
class Config:
    seed: int = SEED
    learners: int = 10_000
    skills: int = 500
    content: int = 2_000
    attempts: int = 500_000
    cold_start_share: float = 0.08        # learners who enrol but never attempt anything
    withdraw_share: float = 0.12          # learners who stop early and are later withdrawn
    follow_prob: float = 0.80             # learner takes the next recommended item
    retry_prob: float = 0.55              # learner retries a failed assessed item
    abandon_prob: float = 0.04
    # labelled edge cases, per 100,000 attempts
    rate_prereq_violation: float = 12
    rate_timestamp_invalid: float = 20
    rate_missing_skill: float = 3
    rate_future_mastery: float = 12
    rate_path_loop: float = 4
    min_count: int = 2                    # floor so tiny datasets still show every edge case

    def __post_init__(self):
        if self.skills % SKILLS_PER_COURSE:
            raise ValueError(f"skills must be a multiple of {SKILLS_PER_COURSE} (one course = 4 topics x 5 tiers)")
        if self.content < self.skills * 2:
            raise ValueError("content must be at least 2 x skills so every skill has two assessed items")

    @property
    def courses(self):
        return self.skills // SKILLS_PER_COURSE

    def count(self, rate_per_100k: float) -> int:
        return max(self.min_count, math.ceil(rate_per_100k * self.attempts / 100_000))
