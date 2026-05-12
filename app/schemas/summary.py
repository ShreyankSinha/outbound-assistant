from __future__ import annotations

from pydantic import BaseModel, Field


class SessionSummary(BaseModel):
    summary: str
    follow_up_actions: list[str] = Field(default_factory=list)
