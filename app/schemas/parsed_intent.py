from __future__ import annotations

from pydantic import BaseModel, Field, model_validator


class ParsedIntent(BaseModel):
    customer_id: int | None = None
    customer_name: str | None = None
    phone_number: str | None = None
    call_objective: str = ""
    topic_one: str | None = None
    topic_two: str | None = None
    single_topic: bool = True
    issue_type: str = "general_follow_up"
    amount: str | None = None
    due_date: str | None = None
    reference_number: str | None = None
    desired_resolution: str = "clarify situation and seek resolution"
    raw_instruction: str = ""
    extracted_notes: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _normalize_topics(self) -> "ParsedIntent":
        if not self.call_objective:
            self.call_objective = self.raw_instruction or self.desired_resolution or self.issue_type.replace("_", " ")
        return self
