# Entity-relationship diagram

```mermaid
erDiagram
  Course ||--o{ Skill : "owns"
  Course ||--o{ ContentItem : "offers"
  Skill ||--o{ SkillPrerequisite : "requires"
  Skill ||--o{ SkillPrerequisite : "is prerequisite in"
  ContentItem ||--|{ ContentSkill : "maps"
  Skill ||--o{ ContentSkill : "taught by"
  Learner ||--o{ LearningPath : "enrols"
  Course ||--o{ LearningPath : "followed in"
  LearningPath ||--|{ LearningPathEvent : "history"
  Learner ||--o{ Attempt : "makes"
  ContentItem ||--o{ Attempt : "attempted in"
  LearningPath ||--o{ Attempt : "contains"
  Attempt ||--o{ AssessmentResult : "evidence"
  Skill ||--o{ AssessmentResult : "measured"
  Learner ||--o{ Recommendation : "receives"
  LearningPath ||--o{ Recommendation : "for"
  ContentItem |o--o{ Recommendation : "suggests"
  Recommendation |o--o{ Attempt : "followed by"
  Recommendation |o--o| LearningPathEvent : "assigned as step"
  Learner {
    text learner_id PK
    text display_name
    text email
    text country
    text prior_level
    text cohort
  }
  Course {
    text course_id PK
    text course_code
    text title
    text domain
    integer sequence_in_domain
    text level
  }
  Skill {
    text skill_id PK
    text course_id FK
    text skill_name
    text topic
    integer tier
    text status
  }
  SkillPrerequisite {
    text prerequisite_id PK
    text skill_id FK
    text prerequisite_skill_id FK
    text relation_type
    real min_mastery
    boolean cross_course
  }
  ContentItem {
    text content_id PK
    text course_id FK
    text title
    text format
    integer difficulty
    integer est_minutes
  }
  ContentSkill {
    text content_skill_id PK
    text content_id FK
    text skill_id FK
    real weight
    boolean is_primary
  }
  LearningPath {
    text path_id PK
    text learner_id FK
    text course_id FK
    timestamp created_at
    text status
    timestamp status_changed_at
  }
  LearningPathEvent {
    text event_id PK
    text path_id FK
    integer event_seq
    text event_type
    timestamp event_at
    text from_status
  }
  Attempt {
    text attempt_id PK
    text learner_id FK
    text content_id FK
    text path_id FK
    text recommendation_id FK
    integer attempt_no
  }
  AssessmentResult {
    text result_id PK
    text attempt_id FK
    text learner_id FK
    text skill_id FK
    text content_id FK
    real evidence_weight
  }
  Recommendation {
    text recommendation_id PK
    text learner_id FK
    text path_id FK
    text content_id FK
    text skill_id FK
    timestamp recommended_at
  }
```

Many-to-many relationships use bridge tables: **ContentSkill** (ContentItem N:M Skill) and **SkillPrerequisite** (Skill N:M Skill, a directed acyclic graph). Optional relationships: `Recommendation.content_id` (null for escalations), `Attempt.recommendation_id`, `Attempt.submitted_at` (abandoned), `Learner.withdrawn_at`, `ContentItem.published_at/retired_at`, `SkillPrerequisite.effective_to`.
