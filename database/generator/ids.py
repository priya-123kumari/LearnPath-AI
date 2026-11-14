"""Deterministic, zero-padded, immutable IDs.

LRN-000001  CRS-000001  SKL-000001  CNT-000001  ATT-LRN-000001-000001  PATH-2026-000001
plus SPR- (prerequisite), CSK- (content-skill bridge), ASR- (assessment result), PEV- (path event), REC- (recommendation).
"""
ID_PATTERNS = {
    "Learner.learner_id": r"^LRN-\d{6}$", "Course.course_id": r"^CRS-\d{6}$", "Skill.skill_id": r"^SKL-\d{6}$",
    "ContentItem.content_id": r"^CNT-\d{6}$", "SkillPrerequisite.prerequisite_id": r"^SPR-\d{6}$",
    "ContentSkill.content_skill_id": r"^CSK-\d{6}$", "Attempt.attempt_id": r"^ATT-LRN-\d{6}-\d{6}$",
    "LearningPath.path_id": r"^PATH-2026-\d{6}$", "AssessmentResult.result_id": r"^ASR-\d{8}$",
    "LearningPathEvent.event_id": r"^PEV-\d{8}$", "Recommendation.recommendation_id": r"^REC-\d{8}$",
}

learner = lambda n: f"LRN-{n:06d}"
course = lambda n: f"CRS-{n:06d}"
skill = lambda n: f"SKL-{n:06d}"
content = lambda n: f"CNT-{n:06d}"
prereq = lambda n: f"SPR-{n:06d}"
content_skill = lambda n: f"CSK-{n:06d}"
attempt = lambda learner_id, n: f"ATT-{learner_id}-{n:06d}"
path = lambda n, year=2026: f"PATH-{year}-{n:06d}"
result = lambda n: f"ASR-{n:08d}"
path_event = lambda n: f"PEV-{n:08d}"
recommendation = lambda n: f"REC-{n:08d}"
gt = lambda n: f"GT-{n:06d}"
