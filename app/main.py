"""DSA Planner: FastAPI application (API + static frontend)."""
from __future__ import annotations

import os
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from . import planner, progress as prog, views
from .catalog import Catalog, base_problems
from .catalog_data import TOPIC_ORDER
from .export import render_markdown
from .models import PlanRequest, ProgressUpdate
from .storage import Store
from .verify import verify_catalog

ROOT = Path(__file__).resolve().parent.parent
FRONTEND_DIR = ROOT / "frontend"
VERIFY_MAX_AGE = timedelta(hours=24)
VERIFY_RETRY_AFTER = timedelta(hours=1)


def get_today() -> date:
    return date.today()


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def get_store(request: Request) -> Store:
    return request.app.state.store


def _age(iso: str | None) -> timedelta | None:
    if not iso:
        return None
    try:
        then = datetime.fromisoformat(iso)
    except ValueError:
        return None
    if then.tzinfo is None:
        then = then.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) - then


def _verification_info(ver: dict | None, status: str, note: str = "") -> dict:
    ver = ver or {}
    return {
        "status": status,  # verified | cached | offline | skipped
        "checked_at": ver.get("checked_at"),
        "source": ver.get("source"),
        "paid_removed": len(ver.get("paid", [])),
        "not_found_removed": len(ver.get("not_found", [])),
        "note": note,
    }


def resolve_catalog(request: Request, store: Store, *, verify: bool, force: bool = False) -> tuple[Catalog, dict]:
    """Build the catalog, optionally re-verifying free status against leetcode.com first."""
    cached = store.load_verification()
    cached_ok = cached if cached and cached.get("status") == "verified" else None

    if not verify:
        info = _verification_info(cached_ok, "cached" if cached_ok else "skipped",
                                  "Using the last verification result." if cached_ok else "Live check skipped; using the bundled free-problem list.")
        return Catalog.build(cached_ok), info

    age = _age(cached_ok.get("checked_at")) if cached_ok else None
    fresh = cached_ok is not None and age is not None and age < VERIFY_MAX_AGE
    if fresh and not force:
        return Catalog.build(cached_ok), _verification_info(cached_ok, "verified", "Checked against leetcode.com recently.")

    result = verify_catalog(base_problems(), fetch=request.app.state.fetch_index)
    if result["status"] == "verified":
        store.save_verification(result)
        return Catalog.build(result), _verification_info(result, "verified", "Checked against leetcode.com just now.")
    if cached_ok:
        return Catalog.build(cached_ok), _verification_info(
            cached_ok, "cached", "Could not reach leetcode.com; used the last successful check."
        )
    return Catalog.build(None), _verification_info(
        None, "offline", "Could not reach leetcode.com. Using the bundled list, which only contains free problems."
    )


def cached_catalog(store: Store) -> Catalog:
    ver = store.load_verification()
    return Catalog.build(ver if ver and ver.get("status") == "verified" else None)


def _validate_topics(topics: list[str]) -> tuple[str, ...]:
    bad = [t for t in topics if t not in TOPIC_ORDER]
    if bad:
        raise HTTPException(422, f"Unknown topic(s): {', '.join(bad)}")
    return tuple(dict.fromkeys(topics))


def _params(req: PlanRequest, today: date) -> planner.PlanParams:
    return planner.PlanParams(
        days=req.days,
        hours_per_day=req.hours_per_day,
        level=req.level,
        weak_topics=_validate_topics(req.weak_topics),
        start_date=req.start_date or today,
    )


def create_app(data_dir: str | os.PathLike | None = None, fetch_index=None) -> FastAPI:
    from .verify import fetch_leetcode_index

    app = FastAPI(title="DSA Planner", version="1.0.0")
    app.state.store = Store(data_dir or os.environ.get("DSA_PLANNER_DATA") or ROOT / "data")
    app.state.fetch_index = fetch_index or fetch_leetcode_index

    # ------------------------------------------------------------------ meta
    @app.get("/api/health")
    def health():
        return {"status": "ok", "problems": len(base_problems())}

    @app.get("/api/meta")
    def meta(store: Store = Depends(get_store)):
        catalog = cached_catalog(store)
        ver = store.load_verification()
        status = "verified" if ver and ver.get("status") == "verified" else "bundled"
        return {
            "topics": [{"topic": t, "count": sum(1 for p in catalog.problems if p.topic == t)} for t in catalog.topics],
            "levels": list(planner.LEVELS),
            "statuses": list(prog.STATUSES),
            "catalog_size": len(catalog.problems),
            "verification": _verification_info(ver if status == "verified" else None, status),
        }

    @app.post("/api/catalog/verify")
    def verify_now(request: Request, store: Store = Depends(get_store)):
        catalog, info = resolve_catalog(request, store, verify=True, force=True)
        return {"verification": info, "removed": catalog.removed, "catalog_size": len(catalog.problems)}

    # -------------------------------------------------------------- problems
    def _problem_payload(p, entry: dict | None, in_plan: bool = False) -> dict:
        entry = entry or {}
        return {
            **p.to_dict(),
            "status": entry.get("status", "todo"),
            "note": entry.get("note", ""),
            "updated_on": entry.get("updated_on"),
            "in_plan": in_plan,
        }

    @app.get("/api/problems")
    def list_problems(
        topic: str | None = None,
        difficulty: str | None = None,
        status: str | None = None,
        q: str | None = Query(None, max_length=100),
        store: Store = Depends(get_store),
    ):
        catalog = cached_catalog(store)
        state = store.load_state()
        active = store.load_plan(state["active_plan_id"]) if state["active_plan_id"] else None
        in_plan = {it["slug"] for d in active["days"] for it in d["items"]} if active else set()
        needle = (q or "").strip().lower()
        out = []
        for p in catalog.problems:
            entry = state["progress"].get(p.slug)
            st = (entry or {}).get("status", "todo")
            if topic and p.topic != topic:
                continue
            if difficulty and p.difficulty.lower() != difficulty.lower():
                continue
            if status and st != status:
                continue
            if needle and needle not in p.title.lower() and needle not in p.pattern.lower() and needle not in p.slug:
                continue
            out.append(_problem_payload(p, entry, p.slug in in_plan))
        return {"count": len(out), "problems": out}

    @app.get("/api/problems/{slug}")
    def get_problem(slug: str, store: Store = Depends(get_store)):
        problem = cached_catalog(store).by_slug.get(slug)
        if problem is None:
            raise HTTPException(404, "Unknown problem")
        entry = store.load_state()["progress"].get(slug)
        payload = _problem_payload(problem, entry)
        payload["history"] = list(reversed((entry or {}).get("history", [])))[:10]
        return {"problem": payload}

    @app.put("/api/problems/{slug}")
    def update_problem(slug: str, body: ProgressUpdate, store: Store = Depends(get_store), today: date = Depends(get_today)):
        catalog = cached_catalog(store)
        problem = catalog.by_slug.get(slug)
        if problem is None:
            raise HTTPException(404, "Unknown problem")
        holder: dict = {}

        def mutate(state: dict) -> None:
            holder["entry"] = prog.apply_update(state, slug, body.status, body.note, today, _now_iso())

        store.update_state(mutate)
        return {"problem": _problem_payload(problem, holder["entry"] if holder["entry"]["status"] != "todo" or holder["entry"].get("note") else None)}

    # ----------------------------------------------------------------- plans
    @app.post("/api/plans/preview")
    def preview_plan(req: PlanRequest, request: Request, store: Store = Depends(get_store), today: date = Depends(get_today)):
        catalog, info = resolve_catalog(request, store, verify=False)
        plan = planner.build_plan(catalog, _params(req, today), plan_id="preview", name="preview", created_at=_now_iso(), verification=info)
        return {
            "summary": plan["summary"],
            "days": [{k: d[k] for k in ("day", "date", "kind", "theme", "planned_minutes")} | {"count": len(d["items"])} for d in plan["days"]],
        }

    @app.post("/api/plans", status_code=201)
    def create_plan(req: PlanRequest, request: Request, store: Store = Depends(get_store), today: date = Depends(get_today)):
        catalog, info = resolve_catalog(request, store, verify=req.verify)
        params = _params(req, today)
        name = (req.name or "").strip() or f"{req.days}-day plan, {req.hours_per_day:g} h/day"
        plan = planner.build_plan(
            catalog, params, plan_id=store.new_plan_id(), name=name, created_at=_now_iso(), verification=info
        )
        plan["summary"]["removed_by_verification"] = catalog.removed
        store.save_plan(plan)
        if req.activate:
            store.update_state(lambda s: s.__setitem__("active_plan_id", plan["id"]))
        state = store.load_state()
        return views.plan_view(plan, state["progress"], today)

    @app.get("/api/plans")
    def list_plans(store: Store = Depends(get_store)):
        active_id = store.load_state()["active_plan_id"]
        return {"plans": [views.plan_summary(p, active_id) for p in store.list_plans()]}

    @app.get("/api/plans/active")
    def active_plan(store: Store = Depends(get_store), today: date = Depends(get_today)):
        state = store.load_state()
        plan = store.load_plan(state["active_plan_id"]) if state["active_plan_id"] else None
        return {"plan": views.plan_view(plan, state["progress"], today) if plan else None}

    def _get_plan_or_404(store: Store, plan_id: str) -> dict:
        plan = store.load_plan(plan_id)
        if plan is None:
            raise HTTPException(404, "Plan not found")
        return plan

    @app.get("/api/plans/{plan_id}")
    def get_plan(plan_id: str, store: Store = Depends(get_store), today: date = Depends(get_today)):
        plan = _get_plan_or_404(store, plan_id)
        return views.plan_view(plan, store.load_state()["progress"], today)

    @app.post("/api/plans/{plan_id}/activate")
    def activate_plan(plan_id: str, store: Store = Depends(get_store), today: date = Depends(get_today)):
        plan = _get_plan_or_404(store, plan_id)
        store.update_state(lambda s: s.__setitem__("active_plan_id", plan_id))
        return views.plan_view(plan, store.load_state()["progress"], today)

    @app.post("/api/plans/{plan_id}/replan")
    def replan_plan(plan_id: str, store: Store = Depends(get_store), today: date = Depends(get_today)):
        plan = _get_plan_or_404(store, plan_id)
        state = store.load_state()
        try:
            planner.replan(plan, cached_catalog(store), state["progress"], today, _now_iso())
        except planner.PlanFinished as exc:
            raise HTTPException(409, str(exc))
        store.save_plan(plan)
        return {"plan": views.plan_view(plan, state["progress"], today), "replan": plan["replans"][-1]}

    @app.delete("/api/plans/{plan_id}")
    def delete_plan(plan_id: str, store: Store = Depends(get_store)):
        if not store.delete_plan(plan_id):
            raise HTTPException(404, "Plan not found")

        def mutate(state: dict) -> None:
            if state["active_plan_id"] == plan_id:
                state["active_plan_id"] = None

        store.update_state(mutate)
        return {"deleted": plan_id}

    @app.get("/api/plans/{plan_id}/export")
    def export_plan(plan_id: str, format: str = Query("md", pattern="^(md|json)$"), store: Store = Depends(get_store)):
        plan = _get_plan_or_404(store, plan_id)
        if format == "json":
            return JSONResponse(plan, headers={"Content-Disposition": f'attachment; filename="{plan_id}.json"'})
        text = render_markdown(plan, store.load_state()["progress"])
        return Response(text, media_type="text/markdown; charset=utf-8", headers={"Content-Disposition": f'attachment; filename="{plan_id}.md"'})

    # ------------------------------------------------------------- dashboard
    @app.get("/api/dashboard")
    def dashboard(store: Store = Depends(get_store), today: date = Depends(get_today)):
        state = store.load_state()
        plan = store.load_plan(state["active_plan_id"]) if state["active_plan_id"] else None
        return views.dashboard(plan, state, cached_catalog(store), today)

    # --------------------------------------------------------------- frontend
    if FRONTEND_DIR.is_dir():
        app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
    return app


app = create_app()
