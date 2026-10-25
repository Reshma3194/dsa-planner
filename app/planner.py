"""Plan generation. Pure functions: no I/O, no clock, fully unit-testable.

How a plan is built
-------------------
1. Capacity: days x hours/day. 15% of every day is kept free for revision, so a
   learn day holds `learn_budget` minutes of NEW problems.
2. Structure: every 7th day (for plans of 10+ days) and the last day (for plans
   of 3+ days) are review days that re-solve earlier hard/medium problems.
3. Selection: problems are ranked by tier (core -> important -> stretch). Inside
   a tier we round-robin across topics so a short plan still touches every
   topic. Weak topics are boosted. Problems are taken until capacity is used.
4. Ordering: chosen problems are laid out in roadmap order (topic by topic,
   easy -> hard) and packed into days, pulling a shorter problem forward when the
   next one would not fit.
5. Feasibility: the summary says how much of the core set was covered and what
   it would take (more days, or more hours/day) to cover all of it.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date, timedelta

from .catalog import DIFFICULTY_RANK, Catalog, Problem

LEVELS = ("beginner", "intermediate", "advanced")
BASE_MINUTES = {"Easy": 20, "Medium": 40, "Hard": 65}
LEVEL_FACTOR = {"beginner": 1.5, "intermediate": 1.0, "advanced": 0.8}
REVISION_RESERVE = 0.15   # share of each learn day left free for revising old problems
REVIEW_FRACTION = 0.8     # a re-solve takes ~80% of the first-solve estimate
REVIEW_DAY_FILL = 0.9     # share of a review day's time that gets scheduled
LOOKAHEAD = 8             # how far ahead the packer may look for a problem that fits
MAX_REVIEW_ITEMS = 5
ATTEMPTED = {"solved", "hinted", "redo"}


class PlanFinished(Exception):
    """Raised when asked to replan a plan whose last day is already in the past."""


@dataclass
class PlanParams:
    days: int
    hours_per_day: float
    level: str = "intermediate"
    weak_topics: tuple[str, ...] = field(default_factory=tuple)
    start_date: date = field(default_factory=date.today)


# --------------------------------------------------------------------------- helpers
def estimate_minutes(problem: Problem, level: str) -> int:
    minutes = BASE_MINUTES[problem.difficulty] * LEVEL_FACTOR[level]
    return max(10, int(round(minutes / 5.0)) * 5)


def review_day_numbers(days: int) -> set[int]:
    """1-based numbers of review days for a plan of `days` days."""
    if days < 3:
        return set()
    weekly = {w for w in range(7, days, 7) if w < days - 1} if days >= 10 else set()
    return weekly | {days}


def _learn_day_count(days: int) -> int:
    return days - len(review_day_numbers(days))


def _effective_tier(problem: Problem, level: str) -> int:
    tier = problem.tier
    if level == "advanced" and problem.difficulty == "Easy":
        tier = min(3, tier + 1)  # advanced users: easy problems matter less
    return tier


def _item(problem: Problem, minutes: int, kind: str = "new") -> dict:
    return {
        "slug": problem.slug,
        "title": problem.title,
        "difficulty": problem.difficulty,
        "topic": problem.topic,
        "pattern": problem.pattern,
        "tier": problem.tier,
        "minutes": minutes,
        "kind": kind,
        "url": problem.url,
    }


def _fill_day(remaining: list[dict], budget: int) -> list[dict]:
    """Take items off the front of `remaining` (mutated) until the day is full.

    Looks a few items ahead for one that still fits. An empty day always accepts its
    first item, so progress is guaranteed even when one problem exceeds the budget.
    """
    placed: list[dict] = []
    used = 0
    while remaining:
        for i, it in enumerate(remaining[:LOOKAHEAD]):
            if used == 0 or used + it["minutes"] <= budget:
                placed.append(it)
                used += it["minutes"]
                remaining.pop(i)
                break
        else:
            break
    return placed


def _pack(items: list[dict], budgets: list[int]) -> tuple[list[list[dict]], list[dict]]:
    """Fill days in order with explicit budgets. Returns (items per day, items that did not fit)."""
    remaining = list(items)
    days: list[list[dict]] = []
    for budget in budgets:
        days.append(_fill_day(remaining, budget) if budget > 0 else [])
    return days, remaining


def _pack_balanced(items: list[dict], caps: list[int]) -> tuple[list[list[dict]], list[dict]]:
    """Like _pack, but each day's load is recomputed from what is left, so work is spread evenly.

    `caps` is the maximum minutes each day can hold. With little spare time every day is filled
    to its cap; with lots of spare time work is not front-loaded, so the last days are not empty.
    """
    remaining = list(items)
    days: list[list[dict]] = []
    for di, cap in enumerate(caps):
        if not remaining or cap <= 0:
            days.append([])
            continue
        usable_days = sum(1 for c in caps[di:] if c > 0)
        need = math.ceil(sum(i["minutes"] for i in remaining) / usable_days * 1.1)
        days.append(_fill_day(remaining, min(cap, max(need, remaining[0]["minutes"]))))
    return days, remaining


def _pack_best(items: list[dict], caps: list[int]) -> tuple[list[list[dict]], list[dict]]:
    """Balanced packing first; if that is too tight, fill every day to its cap instead."""
    packed, overflow = _pack_balanced(items, caps)
    if overflow:
        packed, overflow = _pack(items, caps)
    return packed, overflow


def _topics_of(items: list[dict]) -> list[str]:
    seen: list[str] = []
    for it in items:
        if it["topic"] not in seen:
            seen.append(it["topic"])
    return seen


def _day_dict(number: int, start: date, kind: str, budget: int, items: list[dict], theme: str | None = None) -> dict:
    topics = _topics_of(items) if kind == "learn" else []
    return {
        "day": number,
        "date": (start + timedelta(days=number - 1)).isoformat(),
        "kind": kind,
        "theme": theme or (" · ".join(topics) if topics else "Buffer"),
        "topics": topics,
        "budget_minutes": budget,
        "planned_minutes": sum(i["minutes"] for i in items),
        "items": items,
    }


def _round5(x: float) -> int:
    return max(5, int(round(x / 5.0)) * 5)


# --------------------------------------------------------------------------- build
def build_plan(
    catalog: Catalog,
    params: PlanParams,
    *,
    plan_id: str,
    name: str,
    created_at: str,
    verification: dict,
    _refine: bool = True,
) -> dict:
    level = params.level
    weak = set(params.weak_topics)
    daily = int(round(params.hours_per_day * 60))
    learn_budget = int(daily * (1 - REVISION_RESERVE))
    review_nums = review_day_numbers(params.days)
    learn_nums = [d for d in range(1, params.days + 1) if d not in review_nums]

    pool = [p for p in catalog.problems if not (level == "beginner" and p.difficulty == "Hard")]
    minutes = {p.slug: estimate_minutes(p, level) for p in pool}

    # priority keys: lower is picked earlier
    counters: dict[tuple[str, int], int] = {}
    keys: dict[str, tuple] = {}
    for p in sorted(pool, key=lambda q: q.order):
        et = _effective_tier(p, level)
        idx = counters.get((p.topic, et), 0)
        counters[(p.topic, et)] = idx + 1
        keys[p.slug] = (et, idx * (0.5 if p.topic in weak else 1.0), catalog.topic_index(p.topic), p.order)

    capacity = learn_budget * len(learn_nums)
    chosen: list[Problem] = []
    left = capacity
    for p in sorted(pool, key=lambda q: keys[q.slug]):
        if minutes[p.slug] <= left:
            chosen.append(p)
            left -= minutes[p.slug]

    # Pack in roadmap order, spreading work evenly when there is spare capacity.
    # If fragmentation still causes overflow, drop the lowest-priority problem.
    overflow_dropped: list[Problem] = []
    while True:
        ordered = sorted(chosen, key=lambda q: (catalog.topic_index(q.topic), q.order))
        items = [_item(p, minutes[p.slug]) for p in ordered]
        packed, overflow = _pack_best(items, [learn_budget] * len(learn_nums))
        if not overflow:
            break
        worst = max(chosen, key=lambda q: keys[q.slug])
        chosen.remove(worst)
        overflow_dropped.append(worst)

    day_objs: list[dict] = []
    li = 0
    for d in range(1, params.days + 1):
        if d in review_nums:
            day_objs.append(_day_dict(d, params.start_date, "review", daily, [], "Review & re-solve" if d != params.days else "Final review"))
        else:
            day_objs.append(_day_dict(d, params.start_date, "learn", learn_budget, packed[li]))
            li += 1

    _fill_review_days(day_objs, review_nums, daily, minutes, level, params.days)

    summary = _summarize(
        catalog, pool, minutes, keys, chosen, overflow_dropped, day_objs, params, learn_budget, learn_nums
    )
    if _refine and summary["recommendation"]:
        summary["recommendation"] = _refine_recommendation(catalog, params, summary["recommendation"])
        summary["notes"][0] = _gap_note(params, summary)
    return {
        "id": plan_id,
        "name": name,
        "created_at": created_at,
        "params": {
            "days": params.days,
            "hours_per_day": params.hours_per_day,
            "level": level,
            "weak_topics": list(params.weak_topics),
            "start_date": params.start_date.isoformat(),
        },
        "verification": verification,
        "summary": summary,
        "days": day_objs,
        "replans": [],
    }


def _fill_review_days(day_objs, review_nums, daily, minutes, level, total_days) -> None:
    used_slugs: set[str] = set()
    prev = 0
    for r in sorted(review_nums):
        if r == total_days:
            window = [d for d in day_objs if d["kind"] == "learn" and d["day"] < r]
        else:
            window = [d for d in day_objs if d["kind"] == "learn" and prev < d["day"] < r]
        prev = r
        candidates = [it for d in window for it in d["items"]]
        candidates.sort(key=lambda it: (it["slug"] in used_slugs, -DIFFICULTY_RANK[it["difficulty"]], it["tier"]))
        budget = int(daily * REVIEW_DAY_FILL)
        picked: list[dict] = []
        used = 0
        for it in candidates:
            m = _round5(it["minutes"] * REVIEW_FRACTION)
            if len(picked) >= MAX_REVIEW_ITEMS:
                break
            if used + m <= budget or not picked:
                clone = dict(it, kind="review", minutes=m)
                picked.append(clone)
                used += m
                used_slugs.add(it["slug"])
        target = next(d for d in day_objs if d["day"] == r)
        target["items"] = picked
        target["planned_minutes"] = used


def _gap_note(params: PlanParams, s: dict) -> str:
    rec = s["recommendation"] or {}
    text = (
        f"At {params.hours_per_day:g} h/day over {params.days} days this plan covers {s['core_covered']} of "
        f"{s['core_total']} core problems ({s['core_pct']}%)."
    )
    options = []
    if rec.get("days_for_full_core"):
        options.append(f"about {rec['days_for_full_core']} days at this pace")
    if rec.get("hours_for_full_core"):
        options.append(f"roughly {rec['hours_for_full_core']:g} h/day for {params.days} days")
    if options:
        text += " To cover all of them you need " + ", or ".join(options) + "."
    return text


def _refine_recommendation(catalog: Catalog, params: PlanParams, estimate: dict) -> dict:
    """Turn the capacity-based estimate into an exact answer by actually building trial plans.

    The estimate ignores packing slack (a 65-minute problem cannot share a 76-minute day), so
    the true requirement is at or above it. Search upward from the estimate.
    """

    def covers_core(days: int, hours: float) -> bool:
        trial = PlanParams(days, hours, params.level, params.weak_topics, params.start_date)
        plan = build_plan(catalog, trial, plan_id="trial", name="trial", created_at="", verification={}, _refine=False)
        return plan["summary"]["core_pct"] == 100

    def smallest(lo: int, limit: int, ok) -> int | None:
        """Smallest value in [lo, limit] for which ok() holds (exponential, then binary search)."""
        hi, step = lo, 1
        while hi <= limit and not ok(hi):
            lo, hi, step = hi + 1, hi + step, step * 2
        if hi > limit:
            hi = limit
            if lo > limit or not ok(hi):
                return None
        while lo < hi:
            mid = (lo + hi) // 2
            if ok(mid):
                hi = mid
            else:
                lo = mid + 1
        return lo

    days = smallest(max(estimate["days_for_full_core"], params.days + 1), 365, lambda d: covers_core(d, params.hours_per_day))
    half_hours = smallest(int(params.hours_per_day * 2) + 1, 32, lambda h: covers_core(params.days, h / 2))
    return {
        "days_for_full_core": days,
        "hours_for_full_core": half_hours / 2 if half_hours else None,
    }


def _summarize(catalog, pool, minutes, keys, chosen, overflow_dropped, day_objs, params, learn_budget, learn_nums) -> dict:
    level = params.level
    chosen_slugs = {p.slug for p in chosen}
    core = [p for p in pool if _effective_tier(p, level) == 1]
    core_covered = [p for p in core if p.slug in chosen_slugs]
    core_minutes = sum(minutes[p.slug] for p in core)
    pct = round(100 * len(core_covered) / len(core)) if core else 100

    new_items = [it for d in day_objs for it in d["items"] if it["kind"] == "new"]
    review_slots = sum(1 for d in day_objs for it in d["items"] if it["kind"] == "review")
    planned_minutes = sum(d["planned_minutes"] for d in day_objs)

    by_topic = [
        {"topic": t, "count": sum(1 for p in chosen if p.topic == t)}
        for t in catalog.topics
        if any(p.topic == t for p in chosen)
    ]
    by_difficulty = {d: sum(1 for p in chosen if p.difficulty == d) for d in ("Easy", "Medium", "Hard")}

    missing_core = [
        {"slug": p.slug, "title": p.title, "topic": p.topic, "difficulty": p.difficulty}
        for p in sorted(core, key=lambda q: q.order)
        if p.slug not in chosen_slugs
    ]
    dropped = [
        {"slug": p["slug"], "title": p["title"], "topic": p["topic"], "reason": "Core problem that did not fit the time budget"}
        for p in missing_core[:25]
    ]

    recommendation = None
    if missing_core and core_minutes > 0:
        needed_learn = math.ceil(core_minutes / max(learn_budget, 1))
        d = max(needed_learn, 1)
        while _learn_day_count(d) < needed_learn:
            d += 1
        per_day_budget = core_minutes / max(len(learn_nums), 1)
        hours = math.ceil((per_day_budget / (1 - REVISION_RESERVE)) / 60 * 2) / 2
        recommendation = {"days_for_full_core": d, "hours_for_full_core": max(hours, 0.5)}

    notes: list[str] = []
    if missing_core and recommendation:
        notes.append(
            _gap_note(
                params,
                {"core_covered": len(core_covered), "core_total": len(core), "core_pct": pct, "recommendation": recommendation},
            )
        )
    elif len(chosen) == len(pool):
        notes.append("Every problem in the catalog fits in your time. Use the spare time for timed mock rounds.")
    else:
        notes.append("All core problems are covered. Remaining time goes to important and stretch problems.")
    if level == "beginner":
        notes.append("Hard problems are left out at beginner level. Switch the level to include them.")
    if learn_budget < 40:
        notes.append("Daily time is very short, so most days hold a single problem. Consider adding time on weekends.")
    if params.days >= 3:
        notes.append("Review days re-solve earlier problems without hints. Anything you cannot finish alone goes to Redo.")

    return {
        "new_problems": len({it["slug"] for it in new_items}),
        "review_slots": review_slots,
        "planned_minutes": planned_minutes,
        "planned_hours": round(planned_minutes / 60, 1),
        "core_total": len(core),
        "core_covered": len(core_covered),
        "core_pct": pct,
        "by_topic": by_topic,
        "by_difficulty": by_difficulty,
        "missing_core": missing_core[:40],
        "dropped": dropped,
        "recommendation": recommendation,
        "notes": notes,
    }


# --------------------------------------------------------------------------- replan
def _item_priority(item: dict, catalog: Catalog) -> tuple[int, int]:
    p = catalog.by_slug.get(item["slug"])
    return (item["tier"], p.order if p else 0)


def refresh_totals(plan: dict) -> None:
    """Recompute day minutes/themes and plan-level counters after items moved."""
    new_slugs: set[str] = set()
    review_slots = 0
    total = 0
    for d in plan["days"]:
        d["planned_minutes"] = sum(i["minutes"] for i in d["items"])
        if d["kind"] == "learn":
            d["topics"] = _topics_of(d["items"])
            d["theme"] = " · ".join(d["topics"]) if d["topics"] else "Buffer"
        total += d["planned_minutes"]
        for it in d["items"]:
            if it["kind"] == "new":
                new_slugs.add(it["slug"])
            else:
                review_slots += 1
    s = plan["summary"]
    s["new_problems"] = len(new_slugs)
    s["review_slots"] = review_slots
    s["planned_minutes"] = total
    s["planned_hours"] = round(total / 60, 1)


def replan(plan: dict, catalog: Catalog, progress: dict, today: date, now_iso: str) -> dict:
    """Re-flow everything not yet attempted into the remaining learn days (adaptive replanning).

    Problems the user already attempted stay where they are. Pending problems from past
    days and from today onwards are re-packed into today and later learn days. If they no
    longer fit, the lowest-priority ones are dropped (and reported), never silently lost.
    """
    days = plan["days"]
    if not any(date.fromisoformat(d["date"]) >= today for d in days):
        raise PlanFinished("This plan has already ended.")

    params = plan["params"]
    daily = int(round(params["hours_per_day"] * 60))
    learn_budget = int(daily * (1 - REVISION_RESERVE))

    def attempted(slug: str) -> bool:
        return progress.get(slug, {}).get("status", "todo") in ATTEMPTED

    backlog_past: list[dict] = []
    backlog_future: list[dict] = []
    for d in days:
        if d["kind"] != "learn":
            continue
        keep, move = [], []
        for it in d["items"]:
            (keep if attempted(it["slug"]) else move).append(it)
        d["items"] = keep
        if date.fromisoformat(d["date"]) < today:
            backlog_past += move
        else:
            backlog_future += move

    carried = len(backlog_past)

    def roadmap_order(it: dict) -> tuple[int, int]:
        p = catalog.by_slug.get(it["slug"])
        return (catalog.topic_index(it["topic"]), p.order if p else 0)

    backlog = sorted(backlog_past + backlog_future, key=roadmap_order)  # same order the plan was built in
    targets = [d for d in days if d["kind"] == "learn" and date.fromisoformat(d["date"]) >= today]
    budgets = [max(0, learn_budget - sum(i["minutes"] for i in d["items"])) for d in targets]

    dropped: list[dict] = []
    while True:
        packed, overflow = _pack_best(backlog, budgets)
        if not overflow:
            break
        worst = max(backlog, key=lambda it: _item_priority(it, catalog))
        backlog.remove(worst)
        dropped.append(worst)

    for d, new_items in zip(targets, packed):
        d["items"] = sorted(
            d["items"] + new_items,
            key=lambda it: (catalog.topic_index(it["topic"]), catalog.by_slug[it["slug"]].order if it["slug"] in catalog.by_slug else 0),
        )

    for it in dropped:
        plan["summary"]["dropped"].append(
            {
                "slug": it["slug"],
                "title": it["title"],
                "topic": it["topic"],
                "reason": f"Dropped on replan ({today.isoformat()}): not enough time left",
            }
        )
    plan["replans"].append(
        {
            "at": now_iso,
            "on": today.isoformat(),
            "carried_over": carried,
            "rescheduled": sum(len(x) for x in packed),
            "dropped": [it["slug"] for it in dropped],
        }
    )
    refresh_totals(plan)
    return plan
