"""Readable Markdown export of a plan (the 'file of things we are going to practice')."""
from __future__ import annotations

COMPLETED = {"solved", "hinted"}
_STATUS_MARK = {"solved": "x", "hinted": "x", "redo": "~", "todo": " "}


def render_markdown(plan: dict, progress: dict | None = None) -> str:
    progress = progress or {}
    p = plan.get("params", {})
    s = plan.get("summary", {})
    v = plan.get("verification", {})
    lines = [
        f"# {plan.get('name', 'DSA plan')}",
        "",
        f"- Duration: {p.get('days')} days, {p.get('hours_per_day'):g} h/day, level: {p.get('level')}",
        f"- Starts: {p.get('start_date')}",
        f"- New problems: {s.get('new_problems')}  |  Planned time: {s.get('planned_hours')} h",
        f"- Core coverage: {s.get('core_covered')}/{s.get('core_total')} ({s.get('core_pct')}%)",
        f"- Free-tier check: {v.get('status', 'unknown')}",
        "",
        "Legend: `[x]` done, `[~]` redo (needs another solo attempt), `[ ]` pending.",
        "",
    ]
    for note in s.get("notes", []):
        lines.append(f"> {note}")
    if s.get("notes"):
        lines.append("")
    for day in plan.get("days", []):
        label = "Review" if day["kind"] == "review" else day.get("theme", "")
        lines.append(f"## Day {day['day']} - {day['date']} - {label} ({day['planned_minutes']} min)")
        lines.append("")
        if not day["items"]:
            lines.append("_Rest / buffer day._")
        for it in day["items"]:
            status = progress.get(it["slug"], {}).get("status", "todo")
            mark = _STATUS_MARK.get(status, " ")
            tag = " (re-solve)" if it["kind"] == "review" else ""
            lines.append(
                f"- [{mark}] [{it['title']}]({it['url']}) - {it['difficulty']} - {it['topic']} - ~{it['minutes']} min{tag}"
            )
        lines.append("")
    return "\n".join(lines)
