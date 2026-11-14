"""Business rules of the recommendation workflow (backend tier).

The backend owns these rules. The database-tier generator imports them so the synthetic history is produced
by exactly the same logic the API serves.
"""
import os
from datetime import datetime, timezone

UTC = timezone.utc
DAY = 86_400


def ts(y, m, d, hh=0, mm=0, ss=0):
    """Epoch seconds (UTC). Logic works in integer seconds; files and the API use ISO-8601 text."""
    return int(datetime(y, m, d, hh, mm, ss, tzinfo=UTC).timestamp())


def iso(t):
    return None if t is None else datetime.fromtimestamp(int(t), UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_iso(s):
    if s is None or s == "" or (isinstance(s, float) and s != s):
        return None
    s = str(s).strip().replace(" ", "T")
    if len(s) == 10:
        s += "T00:00:00Z"
    if not s.endswith("Z"):
        s = s[:19] + "Z"
    return int(datetime.strptime(s[:20], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC).timestamp())


MODEL_VERSION = "LP-RULES-1.0"        # stamped on every recommendation
MASTERY_MODEL = "EWMA-1.0"            # stamped on every assessment result
AS_OF = ts(2026, 10, 31, 23, 59, 59)  # dataset "today": default as-of for the API; no wall-clock in the logic

# ---- mastery
PASS_PCT = 70.0                       # score_pct >= 70 is a pass
MASTERY_ALPHA = 0.40                  # EWMA step size before evidence weighting
MASTERED_AT = 0.80
PROFICIENT_AT = 0.50
ASSESSED = {"QUIZ", "EXERCISE", "INTERACTIVE", "PROJECT"}
EVIDENCE_WEIGHT = {"QUIZ": 0.70, "EXERCISE": 0.85, "INTERACTIVE": 0.60, "PROJECT": 1.00}

# ---- recommendation
TOP_K = 3
REMEDIATE_BELOW = 0.40                # with >= 2 evidence rows on the skill
UNLOCK_AT = 0.70                      # highest min_mastery any prerequisite rule asks for; passed items stay eligible below it
SPACED_REVIEW_DAYS = 21
LOOP_GUARD_REPEATS = 2                # same item assigned twice without mastery gain -> excluded
LOOP_MIN_GAIN = 0.02
OUTCOME_WINDOW_DAYS = 14              # a recommendation is "accepted" if attempted within 14 days
STALL_AFTER_DAYS = 30                 # a path with no attempt for 30 days becomes STALLED
LOOP_DETECT_REPEATS = 4               # data-quality detector: >= 4 identical consecutive steps without gain

REASON_CODES = {
    "COLD_START_DIAGNOSTIC": "No assessment evidence yet: start with an easy diagnostic item",
    "PREREQ_GAP_FILL": "A path skill is blocked by an unmet prerequisite: close that gap first",
    "REMEDIATE_LOW_MASTERY": "Repeated low scores: easier item on the same skill",
    "NEXT_IN_SEQUENCE": "Prerequisites now met and skill not started",
    "CONTINUE_PRACTICE": "Skill in progress: item matched to current level",
    "STRETCH_CHALLENGE": "Skill mastered: harder item to keep stretching",
    "SPACED_REVIEW": "Mastered skill not practised recently: short review",
    "NO_ELIGIBLE_CONTENT": "No published item passes the eligibility rules: escalated to instructor",
}
EXCLUSION_CODES = ["NOT_PUBLISHED", "PREREQ_NOT_MET", "ALREADY_MASTERED", "ALREADY_PASSED", "LOOP_GUARD"]

# ---- runtime (API)
DB_PATH = os.environ.get("LEARNPATH_DB", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "database", "learnpath.db"))
DATA_DIR = os.environ.get("LEARNPATH_DATA", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "database", "data", "starter"))
