import json
from datetime import timedelta

from conftest import START, make_index

PLAN = {"days": 14, "hours_per_day": 2, "level": "intermediate"}


def create(client, **over):
    body = {**PLAN, "verify": False, **over}
    r = client.post("/api/plans", json=body)
    assert r.status_code == 201, r.text
    return r.json()


def test_health_and_meta(client):
    assert client.get("/api/health").json()["status"] == "ok"
    meta = client.get("/api/meta").json()
    assert meta["catalog_size"] >= 200
    assert len(meta["topics"]) == 18
    assert meta["statuses"] == ["todo", "solved", "hinted", "redo"]


def test_create_plan_writes_json_and_markdown_files(client, data_dir):
    plan = create(client, name="Interview sprint")
    assert plan["name"] == "Interview sprint" and plan["state"] == "active" and plan["day_number"] == 1
    assert (data_dir / "plans" / f"{plan['id']}.json").exists()
    md = (data_dir / "plans" / f"{plan['id']}.md").read_text(encoding="utf-8")
    assert "https://leetcode.com/problems/" in md and "## Day 1" in md
    saved = json.loads((data_dir / "plans" / f"{plan['id']}.json").read_text(encoding="utf-8"))
    assert saved["id"] == plan["id"] and len(saved["days"]) == 14
    assert client.get("/api/plans/active").json()["plan"]["id"] == plan["id"]


def test_preview_does_not_persist(client, data_dir):
    r = client.post("/api/plans/preview", json=PLAN)
    assert r.status_code == 200
    body = r.json()
    assert len(body["days"]) == 14 and body["summary"]["new_problems"] > 0
    assert list((data_dir / "plans").glob("*")) == []
    assert client.get("/api/plans").json()["plans"] == []


def test_input_validation(client):
    for bad in ({"days": 0}, {"days": 400}, {"hours_per_day": 0.1}, {"hours_per_day": 20}, {"level": "godlike"}):
        assert client.post("/api/plans", json={**PLAN, **bad}).status_code == 422, bad
    r = client.post("/api/plans", json={**PLAN, "weak_topics": ["Not A Topic"]})
    assert r.status_code == 422 and "Unknown topic" in r.json()["detail"]
    assert client.put("/api/problems/two-sum", json={}).status_code == 422
    assert client.put("/api/problems/two-sum", json={"status": "finished"}).status_code == 422


def test_dashboard_without_plan(client):
    d = client.get("/api/dashboard").json()
    assert d["has_plan"] is False and d["today_day"] is None
    assert d["stats"]["completed"] == 0 and d["topics"]


def test_marking_progress_flows_into_dashboard(client):
    create(client)
    today = client.get("/api/dashboard").json()["today_day"]
    first, second = today["items"][0], today["items"][1]
    assert today["day"] == 1 and first["status"] == "todo"

    r = client.put(f"/api/problems/{first['slug']}", json={"status": "solved"})
    assert r.status_code == 200 and r.json()["problem"]["status"] == "solved"
    client.put(f"/api/problems/{second['slug']}", json={"status": "redo", "note": "used the editorial"})

    d = client.get("/api/dashboard").json()
    statuses = {it["slug"]: it["status"] for it in d["today_day"]["items"]}
    assert statuses[first["slug"]] == "solved" and statuses[second["slug"]] == "redo"
    assert d["today_day"]["done"] == 1
    assert d["stats"]["solved"] == 1 and d["stats"]["redo"] == 1 and d["stats"]["solo_rate"] == 50
    assert d["stats"]["streak"] == 1
    assert d["plan"]["progress"]["done"] == 1


def test_progress_persists_across_app_restart(make_client, data_dir):
    c1 = make_client()
    c1.put("/api/problems/two-sum", json={"status": "hinted", "note": "n"})
    c2 = make_client()  # new app instance, same data dir
    p = next(x for x in c2.get("/api/problems?q=two sum").json()["problems"] if x["slug"] == "two-sum")
    assert p["status"] == "hinted" and p["note"] == "n"


def test_revision_queue_over_time(client, clock):
    create(client)
    client.put("/api/problems/two-sum", json={"status": "redo"})
    client.put("/api/problems/3sum", json={"status": "hinted"})
    assert client.get("/api/dashboard").json()["revisions"] == []
    clock.set(START + timedelta(days=1))
    assert [r["slug"] for r in client.get("/api/dashboard").json()["revisions"]] == ["two-sum"]
    clock.set(START + timedelta(days=3))
    assert {r["slug"] for r in client.get("/api/dashboard").json()["revisions"]} == {"two-sum", "3sum"}
    client.put("/api/problems/two-sum", json={"status": "solved"})
    assert {r["slug"] for r in client.get("/api/dashboard").json()["revisions"]} == {"3sum"}


def test_plan_state_before_and_after(client, clock):
    create(client, start_date=(START + timedelta(days=3)).isoformat())
    d = client.get("/api/dashboard").json()
    assert d["plan"]["state"] == "upcoming" and d["today_day"] is None and d["upcoming"][0]["day"] == 1
    clock.set(START + timedelta(days=40))
    d = client.get("/api/dashboard").json()
    assert d["plan"]["state"] == "finished"


def test_replan_endpoint_recovers_missed_days(client, clock):
    plan = create(client)
    clock.set(START + timedelta(days=4))  # missed days 1-4 entirely
    d = client.get("/api/dashboard").json()
    assert d["carried_over"]["count"] > 0 and d["plan"]["progress"]["carried_over"] > 0
    r = client.post(f"/api/plans/{plan['id']}/replan")
    assert r.status_code == 200
    out = r.json()
    assert out["replan"]["carried_over"] > 0
    assert out["plan"]["progress"]["carried_over"] == 0
    assert client.get("/api/dashboard").json()["carried_over"]["count"] == 0
    # the replan is persisted
    assert client.get(f"/api/plans/{plan['id']}").json()["replans"]


def test_replan_finished_plan_conflicts(client, clock):
    plan = create(client, days=5)
    clock.set(START + timedelta(days=30))
    assert client.post(f"/api/plans/{plan['id']}/replan").status_code == 409


def test_plans_list_activate_delete(client, data_dir):
    a = create(client, name="A")
    b = create(client, name="B")
    plans = client.get("/api/plans").json()["plans"]
    assert {p["name"] for p in plans} == {"A", "B"}
    assert next(p for p in plans if p["id"] == b["id"])["active"] is True
    assert client.post(f"/api/plans/{a['id']}/activate").status_code == 200
    assert client.get("/api/plans/active").json()["plan"]["id"] == a["id"]
    assert client.delete(f"/api/plans/{a['id']}").status_code == 200
    assert client.get("/api/plans/active").json()["plan"] is None
    assert not (data_dir / "plans" / f"{a['id']}.json").exists()
    assert client.delete(f"/api/plans/{a['id']}").status_code == 404


def test_plan_ids_cannot_escape_the_data_folder(client):
    for pid in ("..%2F..%2Fetc%2Fpasswd", "%2E%2E", "a", "x" * 80, "PLAN-000001", "plan-000001.json"):
        assert client.get(f"/api/plans/{pid}").status_code == 404
    for pid in ("a", "x" * 80, "PLAN-000001", "plan-000001.json", "000000-000000-zz"):
        assert client.delete(f"/api/plans/{pid}").status_code == 404
        assert client.post(f"/api/plans/{pid}/replan").status_code == 404


def test_export_markdown_and_json(client):
    plan = create(client)
    client.put("/api/problems/two-sum", json={"status": "solved"})
    r = client.get(f"/api/plans/{plan['id']}/export")
    assert r.status_code == 200 and "attachment" in r.headers["content-disposition"]
    assert "[Two Sum](https://leetcode.com/problems/two-sum/)" in r.text and "[x]" in r.text
    j = client.get(f"/api/plans/{plan['id']}/export?format=json")
    assert j.json()["id"] == plan["id"]
    assert client.get(f"/api/plans/{plan['id']}/export?format=xml").status_code == 422


def test_problem_filters_and_unknown_slug(client):
    create(client)
    client.put("/api/problems/two-sum", json={"status": "solved"})
    all_p = client.get("/api/problems").json()
    assert all_p["count"] == len(all_p["problems"]) >= 200
    graphs = client.get("/api/problems", params={"topic": "Graphs"}).json()["problems"]
    assert graphs and {p["topic"] for p in graphs} == {"Graphs"}
    hard = client.get("/api/problems", params={"difficulty": "hard"}).json()["problems"]
    assert hard and {p["difficulty"] for p in hard} == {"Hard"}
    solved = client.get("/api/problems", params={"status": "solved"}).json()["problems"]
    assert [p["slug"] for p in solved] == ["two-sum"]
    assert any(p["in_plan"] for p in all_p["problems"])
    assert client.get("/api/problems", params={"q": "trapping"}).json()["problems"][0]["slug"] == "trapping-rain-water"
    assert client.put("/api/problems/not-a-real-problem", json={"status": "solved"}).status_code == 404


# ------------------------------------------------------------- verification
def test_verification_removes_premium_and_records_result(make_client, data_dir):
    index = make_index(paid={"two-sum"}, missing={"ipo"}, difficulty={"valid-anagram": "Medium"})
    client = make_client(fetch=lambda: index)
    r = client.post("/api/catalog/verify").json()
    assert r["verification"]["status"] == "verified" and r["verification"]["paid_removed"] == 1
    assert {x["slug"] for x in r["removed"]} == {"two-sum", "ipo"}
    assert (data_dir / "verified.json").exists()
    slugs = {p["slug"] for p in client.get("/api/problems").json()["problems"]}
    assert "two-sum" not in slugs and "ipo" not in slugs
    assert client.put("/api/problems/two-sum", json={"status": "solved"}).status_code == 404

    plan = client.post("/api/plans", json={"days": 90, "hours_per_day": 4}).json()  # verify=True, cached result
    assert plan["verification"]["status"] == "verified"
    scheduled = {it["slug"] for d in plan["days"] for it in d["items"]}
    assert "two-sum" not in scheduled and "ipo" not in scheduled
    assert {x["slug"] for x in plan["summary"]["removed_by_verification"]} == {"two-sum", "ipo"}


def test_plan_creation_verifies_live_when_no_cache(make_client):
    calls = []

    def fetch():
        calls.append(1)
        return make_index()

    client = make_client(fetch=fetch)
    p1 = client.post("/api/plans", json={"days": 10, "hours_per_day": 2}).json()
    p2 = client.post("/api/plans", json={"days": 10, "hours_per_day": 2}).json()
    assert p1["verification"]["status"] == p2["verification"]["status"] == "verified"
    assert len(calls) == 1, "second plan reuses the fresh cached verification"


def test_offline_falls_back_to_bundled_list(client):
    plan = client.post("/api/plans", json={"days": 10, "hours_per_day": 2}).json()  # default fetch is offline in tests
    assert plan["verification"]["status"] == "offline"
    assert "Could not reach" in plan["verification"]["note"]
    assert plan["summary"]["new_problems"] > 0
    assert client.post("/api/catalog/verify").json()["verification"]["status"] == "offline"


def test_offline_after_success_uses_cached_result(make_client):
    state = {"online": True}

    def fetch():
        if not state["online"]:
            raise RuntimeError("down")
        return make_index(paid={"two-sum"})

    client = make_client(fetch=fetch)
    assert client.post("/api/catalog/verify").json()["verification"]["status"] == "verified"
    state["online"] = False
    again = client.post("/api/catalog/verify").json()
    assert again["verification"]["status"] == "cached" and {x["slug"] for x in again["removed"]} == {"two-sum"}


def test_partial_index_is_rejected():
    from app.catalog import base_problems
    from app.verify import MIN_EXPECTED_PROBLEMS, VerificationError, verify_catalog

    def tiny():
        raise VerificationError("only 3 problems returned")

    res = verify_catalog(base_problems(), fetch=tiny)
    assert res["status"] == "offline" and "only 3" in res["error"]
    assert MIN_EXPECTED_PROBLEMS >= 1000


# ------------------------------------------------------------------ storage
def test_corrupt_state_file_is_quarantined_not_fatal(make_client, data_dir):
    client = make_client()
    client.put("/api/problems/two-sum", json={"status": "solved"})
    (data_dir / "state.json").write_text("{ this is not json", encoding="utf-8")
    d = client.get("/api/dashboard").json()  # does not crash, starts fresh
    assert d["stats"]["completed"] == 0
    assert list(data_dir.glob("state.json.corrupt-*"))
    assert client.put("/api/problems/two-sum", json={"status": "solved"}).status_code == 200


def test_no_temp_files_left_behind(client, data_dir):
    create(client)
    client.put("/api/problems/two-sum", json={"status": "solved"})
    assert not list(data_dir.rglob("*.tmp"))


def test_frontend_is_served(client):
    r = client.get("/")
    assert r.status_code == 200 and "DSA Planner" in r.text
