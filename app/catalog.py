"""Problem catalog: loads the curated free-problem list and applies verification results."""
from __future__ import annotations

from dataclasses import dataclass, replace
from functools import lru_cache

from .catalog_data import CATALOG_ROWS, TOPIC_ORDER

DIFFICULTY = {"E": "Easy", "M": "Medium", "H": "Hard"}
DIFFICULTY_RANK = {"Easy": 0, "Medium": 1, "Hard": 2}


@dataclass(frozen=True)
class Problem:
    slug: str
    title: str
    difficulty: str
    topic: str
    tier: int
    pattern: str
    order: int  # global position: topic roadmap order, then learning order inside the topic

    @property
    def url(self) -> str:
        return f"https://leetcode.com/problems/{self.slug}/"

    def to_dict(self) -> dict:
        return {
            "slug": self.slug,
            "title": self.title,
            "difficulty": self.difficulty,
            "topic": self.topic,
            "tier": self.tier,
            "pattern": self.pattern,
            "url": self.url,
        }


@lru_cache(maxsize=1)
def base_problems() -> tuple[Problem, ...]:
    problems: list[Problem] = []
    order = 0
    for topic in TOPIC_ORDER:
        for slug, title, diff, tier, pattern in CATALOG_ROWS[topic]:
            problems.append(Problem(slug, title, DIFFICULTY[diff], topic, tier, pattern, order))
            order += 1
    return tuple(problems)


class Catalog:
    """An immutable view of the problem list, optionally filtered by verification data."""

    def __init__(self, problems, removed=None):
        self.problems: tuple[Problem, ...] = tuple(problems)
        self.by_slug: dict[str, Problem] = {p.slug: p for p in self.problems}
        self.removed: list[dict] = list(removed or [])
        present = {p.topic for p in self.problems}
        self.topics: list[str] = [t for t in TOPIC_ORDER if t in present]
        self._topic_index = {t: i for i, t in enumerate(TOPIC_ORDER)}

    def topic_index(self, topic: str) -> int:
        return self._topic_index.get(topic, len(TOPIC_ORDER))

    @classmethod
    def build(cls, verification: dict | None = None) -> "Catalog":
        """Apply live-verification results (premium / missing problems are removed)."""
        problems = list(base_problems())
        removed: list[dict] = []
        if verification and verification.get("status") == "verified":
            paid = set(verification.get("paid", []))
            missing = set(verification.get("not_found", []))
            changes = verification.get("difficulty_changes", {})
            kept = []
            for p in problems:
                if p.slug in paid:
                    removed.append({"slug": p.slug, "title": p.title, "reason": "Premium-only on LeetCode"})
                elif p.slug in missing:
                    removed.append({"slug": p.slug, "title": p.title, "reason": "Not found on LeetCode"})
                else:
                    if p.slug in changes:
                        p = replace(p, difficulty=changes[p.slug])
                    kept.append(p)
            problems = kept
        return cls(problems, removed)
