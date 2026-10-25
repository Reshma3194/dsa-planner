"""Plain JSON-file storage (no database).

Layout inside the data directory:
    state.json          settings pointer + per-problem progress + activity log
    verified.json       last live free-tier verification result
    plans/<id>.json     one file per generated plan (the practice set + schedule)
    plans/<id>.md       the same plan as a readable checklist

Writes are atomic (temp file + os.replace) and guarded by a lock so a crash or
two quick requests cannot leave a half-written file.
"""
from __future__ import annotations

import json
import os
import re
import secrets
import threading
from datetime import datetime
from pathlib import Path

from .export import render_markdown

_PLAN_ID = re.compile(r"^[a-z0-9][a-z0-9-]{5,47}$")


def _default_state() -> dict:
    return {"version": 1, "active_plan_id": None, "progress": {}, "activity": []}


class Store:
    def __init__(self, root: str | os.PathLike):
        self.root = Path(root)
        self.plans_dir = self.root / "plans"
        self.plans_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    # ---- low level ------------------------------------------------------
    def _read(self, path: Path, default):
        try:
            with path.open("r", encoding="utf-8") as fh:
                return json.load(fh)
        except FileNotFoundError:
            return default
        except (json.JSONDecodeError, OSError):
            # Keep the unreadable file for inspection instead of crashing or silently losing it.
            try:
                path.replace(path.with_suffix(path.suffix + f".corrupt-{int(datetime.now().timestamp())}"))
            except OSError:
                pass
            return default

    def _write(self, path: Path, data) -> None:
        tmp = path.with_suffix(path.suffix + ".tmp")
        with tmp.open("w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, ensure_ascii=False)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)

    def _write_text(self, path: Path, text: str) -> None:
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, path)

    # ---- state ----------------------------------------------------------
    def load_state(self) -> dict:
        with self._lock:
            state = self._read(self.root / "state.json", None)
            if not isinstance(state, dict):
                return _default_state()
            for key, value in _default_state().items():
                state.setdefault(key, value)
            return state

    def save_state(self, state: dict) -> None:
        with self._lock:
            self._write(self.root / "state.json", state)

    def update_state(self, fn) -> dict:
        """Read-modify-write under one lock. `fn` mutates the state dict in place."""
        with self._lock:
            state = self.load_state()
            fn(state)
            self.save_state(state)
            return state

    # ---- verification ---------------------------------------------------
    def load_verification(self) -> dict | None:
        with self._lock:
            data = self._read(self.root / "verified.json", None)
            return data if isinstance(data, dict) else None

    def save_verification(self, data: dict) -> None:
        with self._lock:
            self._write(self.root / "verified.json", data)

    # ---- plans ----------------------------------------------------------
    @staticmethod
    def new_plan_id() -> str:
        return datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + secrets.token_hex(2)

    @staticmethod
    def valid_plan_id(plan_id: str) -> bool:
        return bool(_PLAN_ID.match(plan_id or ""))

    def _plan_path(self, plan_id: str, suffix: str = ".json") -> Path:
        if not self.valid_plan_id(plan_id):
            raise ValueError("invalid plan id")
        return self.plans_dir / f"{plan_id}{suffix}"

    def load_plan(self, plan_id: str) -> dict | None:
        if not self.valid_plan_id(plan_id):
            return None
        with self._lock:
            data = self._read(self._plan_path(plan_id), None)
            return data if isinstance(data, dict) else None

    def save_plan(self, plan: dict) -> None:
        with self._lock:
            self._write(self._plan_path(plan["id"]), plan)
            self._write_text(self._plan_path(plan["id"], ".md"), render_markdown(plan, self.load_state()["progress"]))

    def delete_plan(self, plan_id: str) -> bool:
        if not self.valid_plan_id(plan_id):
            return False
        with self._lock:
            existed = False
            for suffix in (".json", ".md"):
                try:
                    self._plan_path(plan_id, suffix).unlink()
                    existed = True
                except FileNotFoundError:
                    pass
            return existed

    def list_plans(self) -> list[dict]:
        with self._lock:
            plans = []
            for path in self.plans_dir.glob("*.json"):
                plan = self._read(path, None)
                if isinstance(plan, dict) and "id" in plan:
                    plans.append(plan)
            plans.sort(key=lambda p: p.get("created_at", ""), reverse=True)
            return plans
