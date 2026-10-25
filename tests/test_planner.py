import copy
from datetime import date, timedelta

import pytest

from app.catalog import Catalog
from app.planner import (
    REVISION_RESERVE,
    PlanFinished,
    PlanParams,
    build_plan,
    estimate_minutes,
    replan,
    review_day_numbers,
)

START = date(2026, 10, 26)
CAT = Catalog.build(None)


def make(days, hours, level="intermediate", weak=(), start=START):
    return build_plan(
        CAT,
        PlanParams(days, hours, level, tuple(weak), start),
        plan_id="plan-000001",
        name="t",
        created_at="2026-10-26T10:00:00",
        verification={"status": "skipped"},
    )


def new_slugs(plan):
    return [it["slug"] for d in plan["days"] for it in d["items"] if it["kind"] == "new"]


# ---------------------------------------------------------------- structure
@pytest.mark.parametrize(
    "days,expected",
    [(1, set()), (2, set()), (3, {3}), (7, {7}), (9, {9}), (10, {7, 10}), (14, {7, 14}), (15, {7, 15}), (22, {7, 14, 22}), (30, {7, 14, 21, 28, 30})],
)
def test_review_day_numbers(days, expected):
    assert review_day_numbers(days) == expected


@pytest.mark.parametrize("days,hours,level", [(1, 1, "intermediate"), (7, 2, "beginner"), (30, 2, "intermediate"), (60, 3, "advanced"), (90, 4, "intermediate")])
def test_plan_shape(days, hours, level):
    plan = make(days, hours, level)
    assert len(plan["days"]) == days
    assert [d["day"] for d in plan["days"]] == list(range(1, days + 1))
    for i, d in enumerate(plan["days"]):
        assert d["date"] == (START + timedelta(days=i)).isoformat()
    assert {d["day"] for d in plan["days"] if d["kind"] == "review"} == review_day_numbers(days)


@pytest.mark.parametrize("days,hours", [(7, 2), (14, 1), (30, 2), (45, 3), (90, 4)])
def test_never_over_budget_unless_single_problem(days, hours):
    plan = make(days, hours)
    learn_budget = int(hours * 60 * (1 - REVISION_RESERVE))
    for d in plan["days"]:
        if d["kind"] == "learn" and len(d["items"]) > 1:
            assert d["planned_minutes"] <= learn_budget, d["day"]
        assert d["planned_minutes"] == sum(i["minutes"] for i in d["items"])


def test_no_duplicate_new_problems_and_only_catalog_problems():
    plan = make(60, 3)
    slugs = new_slugs(plan)
    assert len(slugs) == len(set(slugs))
    assert set(slugs) <= set(CAT.by_slug)


def test_items_carry_leetcode_links():
    plan = make(14, 2)
    for d in plan["days"]:
        for it in d["items"]:
            assert it["url"] == f"https://leetcode.com/problems/{it['slug']}/"


# ---------------------------------------------------------------- selection
def test_more_time_means_more_core_coverage():
    a = make(14, 2)["summary"]["core_covered"]
    b = make(30, 2)["summary"]["core_covered"]
    c = make(30, 4)["summary"]["core_covered"]
    assert a < b < c


def test_short_plan_touches_many_topics():
    plan = make(7, 2)
    topics = {it["topic"] for d in plan["days"] for it in d["items"] if it["kind"] == "new"}
    assert len(topics) >= 12


def test_core_problems_come_before_stretch():
    plan = make(14, 2)
    chosen = {it["slug"]: it["tier"] for d in plan["days"] for it in d["items"] if it["kind"] == "new"}
    assert 3 not in chosen.values()  # not enough time for stretch problems while core is unfinished


def test_weak_topics_get_extra_problems():
    base = make(21, 2)["summary"]["by_topic"]
    boosted = make(21, 2, weak=["Graphs", "1-D DP"])["summary"]["by_topic"]
    count = lambda rows, t: next((r["count"] for r in rows if r["topic"] == t), 0)
    assert count(boosted, "Graphs") > count(base, "Graphs")
    assert count(boosted, "1-D DP") > count(base, "1-D DP")


def test_beginner_excludes_hard_and_takes_longer():
    plan = make(30, 2, "beginner")
    difficulties = {it["difficulty"] for d in plan["days"] for it in d["items"] if it["kind"] == "new"}
    assert "Hard" not in difficulties
    inter = make(30, 2, "intermediate")
    assert plan["summary"]["new_problems"] < inter["summary"]["new_problems"]
    assert estimate_minutes(CAT.by_slug["two-sum"], "beginner") > estimate_minutes(CAT.by_slug["two-sum"], "advanced")


def test_generous_plan_schedules_everything_and_spreads_evenly():
    plan = make(90, 4)
    assert plan["summary"]["new_problems"] == len(CAT.problems)
    assert plan["summary"]["core_pct"] == 100
    learn = [d for d in plan["days"] if d["kind"] == "learn"]
    assert all(d["items"] for d in learn), "no empty learn days"
    minutes = [d["planned_minutes"] for d in learn]
    assert max(minutes) - min(minutes) <= 70


def test_tight_plan_reports_gap_and_recommendation():
    s = make(14, 1.5)["summary"]
    assert s["core_pct"] < 100 and s["missing_core"] and s["dropped"]
    rec = s["recommendation"]
    assert rec["days_for_full_core"] > 14 and rec["hours_for_full_core"] > 1.5
    # following the recommendation really does cover the core set
    assert make(rec["days_for_full_core"], 1.5)["summary"]["core_pct"] == 100
    assert any("core problems" in n for n in s["notes"])


def test_review_days_resolve_earlier_problems():
    plan = make(14, 2)
    first_week = {it["slug"] for d in plan["days"][:6] for it in d["items"]}
    review = plan["days"][6]
    assert review["kind"] == "review" and review["items"]
    assert all(it["kind"] == "review" and it["slug"] in first_week for it in review["items"])
    assert review["planned_minutes"] <= int(2 * 60 * 0.9) or len(review["items"]) == 1


def test_one_day_plan_has_no_review_day():
    plan = make(1, 2)
    assert plan["days"][0]["kind"] == "learn" and plan["days"][0]["items"]


def test_plan_is_deterministic():
    assert make(30, 2, weak=["Graphs"]) == make(30, 2, weak=["Graphs"])


def test_removed_problems_never_scheduled():
    cat = Catalog.build({"status": "verified", "paid": ["two-sum", "3sum"], "not_found": [], "difficulty_changes": {}})
    plan = build_plan(cat, PlanParams(30, 3, "intermediate", (), START), plan_id="plan-000002", name="t", created_at="x", verification={})
    slugs = {it["slug"] for d in plan["days"] for it in d["items"]}
    assert "two-sum" not in slugs and "3sum" not in slugs


# ---------------------------------------------------------------- replan
def progress_for(slugs, status="solved"):
    return {s: {"status": status} for s in slugs}


def test_replan_moves_pending_work_forward_and_keeps_attempted():
    plan = make(30, 2)
    before = new_slugs(plan)
    day1, day2 = plan["days"][0], plan["days"][1]
    done = [it["slug"] for it in day1["items"]]
    today = START + timedelta(days=3)  # user skipped days 2 and 3, only did day 1
    result = replan(copy.deepcopy(plan), CAT, progress_for(done), today, "now")

    # attempted problems stay on their original day
    assert [it["slug"] for it in result["days"][0]["items"]] == done
    # skipped past days no longer hold pending work
    assert result["days"][1]["items"] == [] and result["days"][2]["items"] == []
    # moved problems landed on today or later
    moved = {it["slug"] for it in day2["items"]}
    placed = {it["slug"]: d["date"] for d in result["days"] for it in d["items"] if it["kind"] == "new"}
    assert all(placed[s] >= today.isoformat() for s in moved if s in placed)
    assert result["replans"][-1]["carried_over"] >= len(moved)

    after = set(new_slugs(result))
    dropped = set(result["replans"][-1]["dropped"])
    assert after | dropped == set(before)  # nothing silently lost
    assert not (after & dropped)


def test_replan_drops_lowest_priority_when_time_runs_out():
    plan = make(30, 2)
    # almost at the end of the plan with everything still pending
    today = START + timedelta(days=26)
    result = replan(copy.deepcopy(plan), CAT, {}, today, "now")
    dropped = result["replans"][-1]["dropped"]
    assert dropped, "most problems cannot fit in the last days"
    tiers_dropped = [CAT.by_slug[s].tier for s in dropped]
    tiers_kept = [CAT.by_slug[s].tier for s in set(new_slugs(result))]
    assert max(tiers_dropped) >= max(tiers_kept)
    assert any("Dropped on replan" in d["reason"] for d in result["summary"]["dropped"])
    # no kept learn day on/after today exceeds its budget unless it holds one problem
    budget = int(2 * 60 * (1 - REVISION_RESERVE))
    for d in result["days"]:
        if d["kind"] == "learn" and len(d["items"]) > 1 and d["date"] >= today.isoformat():
            assert d["planned_minutes"] <= budget


def test_replan_before_start_changes_nothing_important():
    plan = make(14, 2)
    result = replan(copy.deepcopy(plan), CAT, {}, START - timedelta(days=2), "now")
    assert new_slugs(result) == new_slugs(plan)
    assert result["replans"][-1]["dropped"] == []


def test_replan_on_finished_plan_raises():
    plan = make(10, 2)
    with pytest.raises(PlanFinished):
        replan(plan, CAT, {}, START + timedelta(days=10), "now")


def test_replan_updates_summary_totals():
    plan = make(30, 2)
    result = replan(copy.deepcopy(plan), CAT, {}, START + timedelta(days=26), "now")
    assert result["summary"]["new_problems"] == len(set(new_slugs(result)))
    assert result["summary"]["planned_minutes"] == sum(d["planned_minutes"] for d in result["days"])
