import sys
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.catalog import base_problems  # noqa: E402
from app.main import create_app, get_today  # noqa: E402
from app.verify import VerificationError  # noqa: E402

START = date(2026, 10, 26)


class Clock:
    """Mutable 'today' injected into the app so tests can move through time."""

    def __init__(self, today: date):
        self.today = today

    def set(self, day: date) -> None:
        self.today = day


def offline_fetch():
    raise VerificationError("network disabled in tests")


def make_index(paid=(), missing=(), difficulty=None):
    """A fake LeetCode index containing every catalog problem (minus `missing`) plus filler."""
    difficulty = difficulty or {}
    index = {}
    for p in base_problems():
        if p.slug in missing:
            continue
        index[p.slug] = {"difficulty": difficulty.get(p.slug, p.difficulty), "paid_only": p.slug in paid}
    for i in range(1200):  # a real index has thousands of entries
        index[f"filler-{i}"] = {"difficulty": "Easy", "paid_only": False}
    return index


@pytest.fixture
def clock():
    return Clock(START)


@pytest.fixture
def make_client(tmp_path, clock):
    def _make(fetch=offline_fetch):
        app = create_app(tmp_path / "data", fetch_index=fetch)
        app.dependency_overrides[get_today] = lambda: clock.today
        return TestClient(app)

    return _make


@pytest.fixture
def client(make_client):
    return make_client()


@pytest.fixture
def data_dir(tmp_path):
    return tmp_path / "data"
