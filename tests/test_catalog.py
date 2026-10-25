import re

from app.catalog import DIFFICULTY_RANK, Catalog, base_problems
from app.catalog_data import CATALOG_ROWS, TOPIC_ORDER

# Problems that require LeetCode Premium. None of them may ever appear in the catalog.
KNOWN_PREMIUM = {
    "alien-dictionary", "graph-valid-tree", "number-of-connected-components-in-an-undirected-graph",
    "meeting-rooms", "meeting-rooms-ii", "encode-and-decode-strings", "walls-and-gates", "wiggle-sort",
    "maximum-depth-of-n-ary-tree-premium", "shortest-word-distance", "paint-house", "paint-fence",
    "missing-ranges", "strobogrammatic-number", "serialize-and-deserialize-n-ary-tree", "closest-leaf-in-a-binary-tree",
    "line-reflection", "unique-word-abbreviation", "design-hit-counter", "design-tic-tac-toe", "the-maze",
    "find-leaves-of-binary-tree", "binary-tree-vertical-order-traversal", "moving-average-from-data-stream",
    "android-unlock-patterns", "lonely-pixel-i", "sentence-screen-fitting", "plus-one-linked-list",
}


def test_catalog_is_substantial_and_consistent():
    problems = base_problems()
    assert len(problems) >= 200
    assert set(TOPIC_ORDER) == set(CATALOG_ROWS)


def test_slugs_unique_and_well_formed():
    slugs = [p.slug for p in base_problems()]
    assert len(slugs) == len(set(slugs))
    assert all(re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", s) for s in slugs)


def test_no_premium_problems_in_catalog():
    assert KNOWN_PREMIUM.isdisjoint({p.slug for p in base_problems()})


def test_fields_are_valid():
    for p in base_problems():
        assert p.difficulty in DIFFICULTY_RANK
        assert p.tier in (1, 2, 3)
        assert p.topic in TOPIC_ORDER
        assert p.title.strip() and p.pattern.strip()
        assert p.url == f"https://leetcode.com/problems/{p.slug}/"


def test_every_topic_has_core_or_important_problems():
    for topic in TOPIC_ORDER:
        tiers = {p.tier for p in base_problems() if p.topic == topic}
        assert tiers & {1, 2}, topic


def test_order_follows_roadmap():
    problems = base_problems()
    assert [p.order for p in problems] == list(range(len(problems)))
    topic_positions = [TOPIC_ORDER.index(p.topic) for p in problems]
    assert topic_positions == sorted(topic_positions)


def test_verification_removes_paid_missing_and_updates_difficulty():
    ver = {
        "status": "verified",
        "paid": ["two-sum"],
        "not_found": ["ipo"],
        "difficulty_changes": {"valid-anagram": "Medium"},
    }
    cat = Catalog.build(ver)
    assert "two-sum" not in cat.by_slug and "ipo" not in cat.by_slug
    assert cat.by_slug["valid-anagram"].difficulty == "Medium"
    reasons = {r["slug"]: r["reason"] for r in cat.removed}
    assert "Premium" in reasons["two-sum"] and "Not found" in reasons["ipo"]


def test_non_verified_result_is_ignored():
    cat = Catalog.build({"status": "offline", "paid": ["two-sum"]})
    assert "two-sum" in cat.by_slug and cat.removed == []
