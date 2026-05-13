from __future__ import annotations

from pydantic import BaseModel, Field


class ParsedIntent(BaseModel):
    customer_id: int | None = None
    issue_type: str = "general_follow_up"
    customer_name: str | None = None
    phone_number: str | None = None
    amount: str | None = None
    due_date: str | None = None
    reference_number: str | None = None
    desired_resolution: str = "clarify situation and seek resolution"
    raw_instruction: str
    extracted_notes: list[str] = Field(default_factory=list)
