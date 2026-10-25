"""Per-problem progress, spaced revision and streaks.

Statuses
    todo    not attempted yet (default, never stored without a note)
    solved  solved on your own
    hinted  solved, but needed hints
    redo    used AI / the editorial / gave up: must be re-solved alone

Revision queue: `redo` problems come back 1 day after you marked them, `hinted`
ones after 3 days. Marking a problem `solved` takes it out of the queue.
"""
from __future__ import annotations

from datetime import date, timedelta

STATUSES = ("todo", "solved", "hinted", "redo")
ATTEMPTED = {"solved", "hinted", "redo"}
COMPLETED = {"solved", "hinted"}
REVISION_DELAY_DAYS = {"redo": 1, "hinted": 3}
HISTORY_LIMIT = 20


def status_of(progress: dict, slug: str) -> str:
    return progress.get(slug, {}).get("status", "todo")


def apply_update(state: dict, slug: str, status: str | None, note: str | None, today: date, now_iso: str) -> dict:
    """Mutate `state` for one problem. Returns the resulting progress entry (or a blank one)."""
    entry = state["progress"].get(slug) or {"status": "todo", "note": "", "updated_at": None, "updated_on": None, "history": []}
    if status is not None:
        entry["status"] = status
        entry["updated_at"] = now_iso
        entry["updated_on"] = today.isoformat()
        entry["history"] = (entry.get("history", []) + [{"status": status, "at": now_iso}])[-HISTORY_LIMIT:]
        if status in ATTEMPTED:
            activity = set(state["activity"])
            activity.add(today.isoformat())
            state["activity"] = sorted(activity)
    if note is not None:
        entry["note"] = note.strip()
    if entry["status"] == "todo" and not entry.get("note"):
        state["progress"].pop(slug, None)
    else:
        state["progress"][slug] = entry
    return entry


def revision_queue(progress: dict, catalog, today: date) -> list[dict]:
    due_items = []
    for slug, entry in progress.items():
        delay = REVISION_DELAY_DAYS.get(entry.get("status"))
        problem = catalog.by_slug.get(slug)
        if delay is None or problem is None or not entry.get("updated_on"):
            continue
        due = date.fromisoformat(entry["updated_on"]) + timedelta(days=delay)
        if due <= today:
            due_items.append(
                {
                    **problem.to_dict(),
                    "status": entry["status"],
                    "due": due.isoformat(),
                    "days_overdue": (today - due).days,
                }
            )
    due_items.sort(key=lambda x: (-x["days_overdue"], x["tier"], x["title"]))
    return due_items


def streaks(activity: list[str], today: date) -> tuple[int, int]:
    """Return (current_streak, best_streak) from a list of ISO dates with activity."""
    days = sorted({date.fromisoformat(a) for a in activity})
    if not days:
        return 0, 0
    best = run = 1
    for prev, cur in zip(days, days[1:]):
        run = run + 1 if (cur - prev).days == 1 else 1
        best = max(best, run)
    dayset = set(days)
    cursor = today if today in dayset else today - timedelta(days=1)
    current = 0
    while cursor in dayset:
        current += 1
        cursor -= timedelta(days=1)
    return current, best


def overall_stats(progress: dict, catalog, activity: list[str], today: date) -> dict:
    counts = {"solved": 0, "hinted": 0, "redo": 0}
    for slug, entry in progress.items():
        if slug in catalog.by_slug and entry.get("status") in counts:
            counts[entry["status"]] += 1
    attempted = sum(counts.values())
    current, best = streaks(activity, today)
    return {
        "solved": counts["solved"],
        "hinted": counts["hinted"],
        "redo": counts["redo"],
        "completed": counts["solved"] + counts["hinted"],
        "solo_rate": round(100 * counts["solved"] / attempted) if attempted else None,
        "streak": current,
        "best_streak": best,
        "catalog_total": len(catalog.problems),
    }
