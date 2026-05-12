from __future__ import annotations

from pydantic import BaseModel, Field

from app.core.enums import CallState, ConversationState, SessionOutcome
from app.schemas.parsed_intent import ParsedIntent
from app.schemas.transcript import TranscriptEntry


class SessionState(BaseModel):
    session_id: str
    timestamp_start: str
    timestamp_end: str | None = None
    operator_instruction: str
    parsed_intent: ParsedIntent
    call_state: CallState = CallState.INITIATING
    conversation_state: ConversationState = ConversationState.GREETING
    transcript: list[TranscriptEntry] = Field(default_factory=list)
    outcome: SessionOutcome | None = None
    summary: str = ""
    follow_up_actions: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    turn_count: int = 0
    escalation_reason: str | None = None
    resolution_notes: list[str] = Field(default_factory=list)
    customer_last_message: str = ""
    agent_last_message: str = ""
    call_target: str = "mock-customer"
