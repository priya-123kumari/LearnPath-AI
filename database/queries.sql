-- Example analytical queries against database/learnpath.db (sqlite3 database/learnpath.db < database/queries.sql)

-- 1. Current mastery per learner and skill (latest evidence row)
SELECT r.learner_id, r.skill_id, s.skill_name, r.mastery_after, r.mastery_level, r.evidence_count
FROM assessment_results r JOIN skills s ON s.skill_id = r.skill_id
WHERE r.evidence_count = (SELECT MAX(evidence_count) FROM assessment_results x WHERE x.learner_id = r.learner_id AND x.skill_id = r.skill_id)
ORDER BY r.learner_id, r.skill_id LIMIT 20;

-- 2. Acceptance and pass rate by reason code
SELECT reason_code, COUNT(*) AS recs,
       ROUND(AVG(status = 'ACCEPTED'), 3) AS acceptance_rate,
       ROUND(AVG(CASE WHEN outcome IN ('COMPLETED_PASS', 'COMPLETED_FAIL') THEN outcome = 'COMPLETED_PASS' END), 3) AS pass_rate
FROM recommendations GROUP BY reason_code ORDER BY recs DESC;

-- 3. Full trail of one learning path (append-only history)
SELECT event_seq, event_type, event_at, from_status, to_status, content_id, skill_id, recommendation_id, mastery_snapshot
FROM learning_path_events WHERE path_id = 'PATH-2026-000005' ORDER BY event_seq;

-- 4. Skills without published content (content coverage gap)
SELECT s.skill_id, s.skill_name FROM skills s
WHERE NOT EXISTS (SELECT 1 FROM content_skills cs JOIN content_items i ON i.content_id = cs.content_id
                  WHERE cs.skill_id = s.skill_id AND i.status = 'PUBLISHED');

-- 5. Labelled anomalies (audit table, never read by the recommender)
SELECT issue_type, COUNT(*) FROM audit_ground_truth GROUP BY issue_type;
