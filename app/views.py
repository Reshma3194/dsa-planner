"""Builds API payloads by merging plans, catalog and progress. No I/O here."""
from __future__ import annotations

import copy
from datetime import date

from .progress import COMPLETED, overall_stats, revision_queue, status_of


def plan_view(plan: dict, progress: dict, today: date) -> dict:
    """A plan with live status merged into every item, plus per-day and plan-level counters."""
    view = copy.deepcopy(plan)
    start = date.fromisoformat(view["params"]["start_date"])
    total_days = view["params"]["days"]
    end = date.fromisoformat(view["days"][-1]["date"]) if view["days"] else start

    unique_new: dict[str, str] = {}
    for d in view["days"]:
        d_date = date.fromisoformat(d["date"])
        d["state"] = "past" if d_date < today else "today" if d_date == today else "upcoming"
        done = 0
        pending = 0
        for it in d["items"]:
            it["status"] = status_of(progress, it["slug"])
            if it["status"] in COMPLETED:
                done += 1
            if it["status"] == "todo":
                pending += 1
            if it["kind"] == "new":
                unique_new[it["slug"]] = it["status"]
        d["done"] = done
        d["count"] = len(d["items"])
        d["carried"] = pending if d["state"] == "past" and d["kind"] == "learn" else 0

    if today < start:
        state, day_number = "upcoming", 0
    elif today > end:
        state, day_number = "finished", total_days + 1
    else:
        state, day_number = "active", (today - start).days + 1

    plan_total = len(unique_new)
    plan_done = sum(1 for s in unique_new.values() if s in COMPLETED)
    view["state"] = state
    view["day_number"] = day_number
    view["end_date"] = end.isoformat()
    view["progress"] = {
        "total": plan_total,
        "done": plan_done,
        "pct": round(100 * plan_done / plan_total) if plan_total else 0,
        "carried_over": sum(d["carried"] for d in view["days"]),
    }
    return view


def plan_summary(plan: dict, active_id: str | None) -> dict:
    last = plan["days"][-1]["date"] if plan.get("days") else plan["params"]["start_date"]
    return {
        "id": plan["id"],
        "name": plan["name"],
        "created_at": plan["created_at"],
        "days": plan["params"]["days"],
        "hours_per_day": plan["params"]["hours_per_day"],
        "level": plan["params"]["level"],
        "start_date": plan["params"]["start_date"],
        "end_date": last,
        "new_problems": plan["summary"]["new_problems"],
        "active": plan["id"] == active_id,
    }


def topic_progress(view: dict | None, progress: dict, catalog) -> list[dict]:
    """Per-topic totals: over the active plan's problems if there is one, else the whole catalog."""
    if view is not None:
        slugs = {}
        for d in view["days"]:
            for it in d["items"]:
                if it["kind"] == "new":
                    slugs[it["slug"]] = it["topic"]
        topics = [t for t in catalog.topics if t in set(slugs.values())]
        bucket = {t: [s for s, tp in slugs.items() if tp == t] for t in topics}
    else:
        topics = list(catalog.topics)
        bucket = {t: [p.slug for p in catalog.problems if p.topic == t] for t in topics}
    rows = []
    for t in topics:
        statuses = [status_of(progress, s) for s in bucket[t]]
        rows.append(
            {
                "topic": t,
                "total": len(statuses),
                "done": sum(1 for s in statuses if s in COMPLETED),
                "solo": sum(1 for s in statuses if s == "solved"),
                "redo": sum(1 for s in statuses if s == "redo"),
            }
        )
    return rows


def dashboard(plan: dict | None, state: dict, catalog, today: date) -> dict:
    progress = state["progress"]
    stats = overall_stats(progress, catalog, state["activity"], today)
    payload: dict = {
        "today": today.isoformat(),
        "has_plan": plan is not None,
        "plan": None,
        "today_day": None,
        "upcoming": [],
        "carried_over": {"count": 0, "items": []},
        "revisions": revision_queue(progress, catalog, today),
        "stats": stats,
    }
    view = None
    if plan is not None:
        view = plan_view(plan, progress, today)
        payload["plan"] = {
            "id": view["id"],
            "name": view["name"],
            "state": view["state"],
            "day_number": view["day_number"],
            "total_days": view["params"]["days"],
            "start_date": view["params"]["start_date"],
            "end_date": view["end_date"],
            "verification": view["verification"],
            "progress": view["progress"],
            "hours_per_day": view["params"]["hours_per_day"],
        }
        payload["today_day"] = next((d for d in view["days"] if d["state"] == "today"), None)
        payload["upcoming"] = [
            {k: d[k] for k in ("day", "date", "kind", "theme", "planned_minutes", "count")}
            for d in view["days"]
            if d["state"] == "upcoming"
        ][:4]
        carried = [
            {**it, "from_day": d["day"], "from_date": d["date"]}
            for d in view["days"]
            if d["carried"]
            for it in d["items"]
            if it["status"] == "todo" and it["kind"] == "new"
        ]
        payload["carried_over"] = {"count": len(carried), "items": carried[:6]}
    payload["topics"] = topic_progress(view, progress, catalog)
    return payload
