"""Unit tests of the backend business rules on a hand-built catalogue (known inputs -> known decisions)."""
from backend.config import ts, DAY
from backend.engine import Catalog, Item, LearnerState, ewma, mastery_level, recommend, replay, target_difficulty

T0 = ts(2026, 3, 1)


def catalog(retire_all=False, eff_to=None):
    skills = {"S1": dict(course_id="C1", tier=1, topic="t", name="Foundations of T"),
              "S2": dict(course_id="C1", tier=2, topic="t", name="Core T")}
    prereqs = {"S2": [("S1", 0.7, ts(2025, 12, 1), eff_to)]}
    ret = T0 - DAY if retire_all else None
    items = {
        "A1": Item("A1", "C1", "S1 quiz", "QUIZ", 1, True, 20, "PUBLISHED", ts(2025, 12, 1), ret, (("S1", 1.0),), "S1"),
        "A2": Item("A2", "C1", "S1 video", "VIDEO", 1, False, None, "PUBLISHED", ts(2025, 12, 1), ret, (("S1", 1.0),), "S1"),
        "B1": Item("B1", "C1", "S2 exercise", "EXERCISE", 2, True, 50, "PUBLISHED", ts(2025, 12, 1), ret, (("S2", 1.0),), "S2"),
    }
    return Catalog(skills, prereqs, items)


def test_ewma_known_values():
    # quiz weight .7, difficulty 1 -> s_eff = 0.8*0.85 = 0.68 ; 0 + 0.4*0.7*0.68 = 0.1904
    assert ewma(0.0, 80, 0.7, 1) == 0.1904
    assert ewma(0.5, 100, 1.0, 5) == round(0.5 + 0.4 * (1.0 - 0.5), 4)        # capped at 1.0
    assert mastery_level(0.0, 0) == "NOT_STARTED" and mastery_level(0.8, 3) == "MASTERED" and mastery_level(0.5, 1) == "PROFICIENT"
    assert target_difficulty(0) == 1 and target_difficulty(0.5) == 3 and target_difficulty(1) == 5


def test_cold_start_recommends_only_eligible_items_with_reason():
    res = recommend(catalog(), LearnerState(), [("P1", "C1")], T0, explain=True)
    ids = [r["content_id"] for r in res["recs"]]
    assert "B1" not in ids, "S2 needs S1 >= 0.7: must not be recommended"
    assert ids[0] == "A1" and res["recs"][0]["reason_code"] == "COLD_START_DIAGNOSTIC"
    assert all(r["reason_code"] and len(r["rationale"]) > 20 for r in res["recs"])
    assert res["excluded"]["PREREQ_NOT_MET"] == 1


def test_prerequisite_unlocks_after_mastery():
    st = LearnerState()
    st.mastery["S1"], st.evidence["S1"], st.total_evidence = 0.75, 3, 3
    st.item_stats["A1"] = [3, 3, 0]
    res = recommend(catalog(), st, [("P1", "C1")], T0)
    b1 = [r for r in res["recs"] if r["content_id"] == "B1"]
    assert b1 and b1[0]["reason_code"] == "NEXT_IN_SEQUENCE" and b1[0]["prereqs_checked"] == 1


def test_effective_dated_prerequisite_stops_gating_after_effective_to():
    cat = catalog(eff_to=ts(2026, 2, 1))
    res = recommend(cat, LearnerState(), [("P1", "C1")], T0)
    assert "B1" in [r["content_id"] for r in res["recs"]]


def test_loop_guard_excludes_item_assigned_twice_without_gain():
    st = LearnerState()
    st.record_step("P1", "A1", "S1"); st.record_step("P1", "A1", "S1")
    res = recommend(catalog(), st, [("P1", "C1")], T0, explain=True)
    assert "A1" not in [r["content_id"] for r in res["recs"]] and res["excluded"].get("LOOP_GUARD") == 1


def test_escalation_when_nothing_is_eligible():
    res = recommend(catalog(retire_all=True), LearnerState(), [("P1", "C1")], T0)
    assert res["escalated"] and res["recs"][0]["reason_code"] == "NO_ELIGIBLE_CONTENT" and res["recs"][0]["content_id"] is None


def test_replay_ignores_future_and_abandoned_attempts():
    cat = catalog()
    rows = [dict(attempt_id="X-1", content_id="A1", status="COMPLETED", score_pct=80.0, passed=1, started_at=T0 - 100, submitted_at=T0 - 50),
            dict(attempt_id="X-2", content_id="A1", status="ABANDONED", score_pct=None, passed=None, started_at=T0 - 40, submitted_at=None),
            dict(attempt_id="X-3", content_id="A1", status="COMPLETED", score_pct=100.0, passed=1, started_at=T0 + 10, submitted_at=T0 + 60)]
    st = replay(cat, rows, as_of=T0)
    assert st.mastery["S1"] == 0.1904 and st.evidence["S1"] == 1          # future attempt X-3 not used
    assert replay(cat, rows).evidence["S1"] == 2
