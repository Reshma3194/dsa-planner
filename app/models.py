"""Request models."""
from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class PlanRequest(BaseModel):
    days: int = Field(30, ge=1, le=365, description="Days until the interview")
    hours_per_day: float = Field(2.0, ge=0.5, le=16, description="Hours you can practice per day")
    level: Literal["beginner", "intermediate", "advanced"] = "intermediate"
    weak_topics: list[str] = Field(default_factory=list, max_length=18)
    start_date: date | None = None
    name: str | None = Field(None, max_length=80)
    verify: bool = True
    activate: bool = True


class ProgressUpdate(BaseModel):
    status: Literal["todo", "solved", "hinted", "redo"] | None = None
    note: str | None = Field(None, max_length=4000)

    @model_validator(mode="after")
    def _something_to_update(self):
        if self.status is None and self.note is None:
            raise ValueError("Provide a status, a note, or both.")
        return self
