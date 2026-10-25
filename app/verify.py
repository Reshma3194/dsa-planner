"""Live free-tier verification against leetcode.com.

LeetCode has no official public API. We use two widely used public endpoints
(the legacy REST index and the GraphQL problem list). Only metadata is read:
slug, difficulty and the paid-only flag. If neither endpoint is reachable
(offline, blocked, changed), verification reports "offline" and the app falls
back to the bundled catalog, which only contains problems that are free.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable

import httpx

REST_URL = "https://leetcode.com/api/problems/algorithms/"
GRAPHQL_URL = "https://leetcode.com/graphql"
MIN_EXPECTED_PROBLEMS = 1000  # a real index has thousands; fewer means a partial/blocked response
_LEVELS = {1: "Easy", 2: "Medium", 3: "Hard"}
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; dsa-planner/1.0; personal study tool)",
    "Referer": "https://leetcode.com/problemset/",
}
_GQL_QUERY = """
query problemsetQuestionList($categorySlug: String, $limit: Int, $skip: Int, $filters: QuestionListFilterInput) {
  problemsetQuestionList: questionList(categorySlug: $categorySlug, limit: $limit, skip: $skip, filters: $filters) {
    total: totalNum
    questions: data { titleSlug difficulty isPaidOnly }
  }
}
"""


class VerificationError(Exception):
    """Raised when the LeetCode index could not be fetched."""


def _rest_index(client: httpx.Client) -> dict[str, dict]:
    resp = client.get(REST_URL)
    resp.raise_for_status()
    index: dict[str, dict] = {}
    for pair in resp.json()["stat_status_pairs"]:
        slug = pair["stat"]["question__title_slug"]
        index[slug] = {
            "difficulty": _LEVELS.get(pair["difficulty"]["level"]),
            "paid_only": bool(pair["paid_only"]),
        }
    return index


def _graphql_index(client: httpx.Client) -> dict[str, dict]:
    index: dict[str, dict] = {}
    skip, page = 0, 100
    for _ in range(80):  # hard cap on pages
        resp = client.post(
            GRAPHQL_URL,
            json={
                "query": _GQL_QUERY,
                "variables": {"categorySlug": "", "skip": skip, "limit": page, "filters": {}},
            },
        )
        resp.raise_for_status()
        block = resp.json()["data"]["problemsetQuestionList"]
        for q in block["questions"]:
            index[q["titleSlug"]] = {"difficulty": q["difficulty"], "paid_only": bool(q["isPaidOnly"])}
        skip += page
        if skip >= block["total"] or not block["questions"]:
            break
    return index


def fetch_leetcode_index(timeout: float = 10.0) -> dict[str, dict]:
    """Return {slug: {"difficulty": str, "paid_only": bool}} for LeetCode's problem set.

    Fails fast: if the host cannot be reached at all (offline, firewall) the second endpoint is
    not tried, so "Generate plan" never hangs for long without internet.
    """
    errors: list[str] = []
    limits = httpx.Timeout(timeout, connect=4.0)
    with httpx.Client(headers=_HEADERS, timeout=limits, follow_redirects=True) as client:
        for name, fn in (("REST", _rest_index), ("GraphQL", _graphql_index)):
            try:
                index = fn(client)
                if len(index) >= MIN_EXPECTED_PROBLEMS:
                    return index
                errors.append(f"{name}: only {len(index)} problems returned")
            except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
                errors.append(f"{name}: cannot connect ({type(exc).__name__})")
                break  # same host, same network: no point trying again
            except Exception as exc:  # blocked, parsing, schema change
                errors.append(f"{name}: {type(exc).__name__}: {exc}")
    raise VerificationError("; ".join(errors))


def verify_catalog(
    problems,
    fetch: Callable[[], dict[str, dict]] = fetch_leetcode_index,
) -> dict:
    """Check every catalog problem against LeetCode. Never raises."""
    checked_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    try:
        index = fetch()
    except Exception as exc:
        return {"status": "offline", "checked_at": checked_at, "error": str(exc)[:500]}

    paid, missing, changes = [], [], {}
    for p in problems:
        info = index.get(p.slug)
        if info is None:
            missing.append(p.slug)
        elif info["paid_only"]:
            paid.append(p.slug)
        elif info["difficulty"] and info["difficulty"] != p.difficulty:
            changes[p.slug] = info["difficulty"]
    return {
        "status": "verified",
        "checked_at": checked_at,
        "source": "leetcode.com",
        "checked": len(problems),
        "paid": paid,
        "not_found": missing,
        "difficulty_changes": changes,
    }
