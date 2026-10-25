from datetime import date, timedelta

from app.catalog import Catalog
from app.progress import apply_update, overall_stats, revision_queue, streaks

CAT = Catalog.build(None)
D0 = date(2026, 10, 26)


def fresh():
    return {"progress": {}, "activity": [], "active_plan_id": None}


def test_status_note_and_cleanup():
    s = fresh()
    apply_update(s, "two-sum", "solved", None, D0, "t1")
    assert s["progress"]["two-sum"]["status"] == "solved"
    apply_update(s, "two-sum", None, "  use a hash map  ", D0, "t2")
    assert s["progress"]["two-sum"]["note"] == "use a hash map"
    assert s["progress"]["two-sum"]["status"] == "solved"  # note-only update keeps the status
    apply_update(s, "two-sum", "todo", "", D0, "t3")
    assert "two-sum" not in s["progress"]  # back to pending with no note: entry removed


def test_note_kept_when_reset_to_todo():
    s = fresh()
    apply_update(s, "two-sum", "redo", "tricky", D0, "t1")
    apply_update(s, "two-sum", "todo", None, D0, "t2")
    assert s["progress"]["two-sum"]["status"] == "todo" and s["progress"]["two-sum"]["note"] == "tricky"


def test_history_is_capped_and_activity_logged():
    s = fresh()
    for i in range(30):
        apply_update(s, "two-sum", "redo" if i % 2 else "hinted", None, D0, f"t{i}")
    assert len(s["progress"]["two-sum"]["history"]) == 20
    assert s["activity"] == [D0.isoformat()]


def test_todo_does_not_count_as_activity():
    s = fresh()
    apply_update(s, "two-sum", "todo", "note only", D0, "t")
    assert s["activity"] == []


def test_revision_queue_timing_and_exit():
    s = fresh()
    apply_update(s, "two-sum", "redo", None, D0, "t")
    apply_update(s, "3sum", "hinted", None, D0, "t")
    apply_update(s, "valid-anagram", "solved", None, D0, "t")
    assert revision_queue(s["progress"], CAT, D0) == []
    day1 = {x["slug"] for x in revision_queue(s["progress"], CAT, D0 + timedelta(days=1))}
    assert day1 == {"two-sum"}
    day3 = revision_queue(s["progress"], CAT, D0 + timedelta(days=3))
    assert {x["slug"] for x in day3} == {"two-sum", "3sum"}
    assert day3[0]["days_overdue"] >= day3[-1]["days_overdue"]  # most overdue first
    apply_update(s, "two-sum", "solved", None, D0 + timedelta(days=3), "t")
    assert {x["slug"] for x in revision_queue(s["progress"], CAT, D0 + timedelta(days=3))} == {"3sum"}


def test_retrying_redo_pushes_it_back():
    s = fresh()
    apply_update(s, "two-sum", "redo", None, D0, "t")
    apply_update(s, "two-sum", "redo", None, D0 + timedelta(days=1), "t")  # failed again
    assert revision_queue(s["progress"], CAT, D0 + timedelta(days=1)) == []
    assert len(revision_queue(s["progress"], CAT, D0 + timedelta(days=2))) == 1


def test_streaks():
    days = [D0 - timedelta(days=n) for n in (0, 1, 2, 5, 6)]
    iso = [d.isoformat() for d in days]
    assert streaks(iso, D0) == (3, 3)
    assert streaks(iso, D0 + timedelta(days=1)) == (3, 3)  # yesterday still counts, streak is alive
    assert streaks(iso, D0 + timedelta(days=2))[0] == 0  # broken
    assert streaks([], D0) == (0, 0)


def test_overall_stats():
    s = fresh()
    apply_update(s, "two-sum", "solved", None, D0, "t")
    apply_update(s, "3sum", "solved", None, D0, "t")
    apply_update(s, "valid-anagram", "hinted", None, D0, "t")
    apply_update(s, "group-anagrams", "redo", None, D0, "t")
    stats = overall_stats(s["progress"], CAT, s["activity"], D0)
    assert (stats["solved"], stats["hinted"], stats["redo"], stats["completed"]) == (2, 1, 1, 3)
    assert stats["solo_rate"] == 50 and stats["streak"] == 1
    assert overall_stats({}, CAT, [], D0)["solo_rate"] is None
