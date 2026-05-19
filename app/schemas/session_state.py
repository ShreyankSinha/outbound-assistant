from __future__ import annotations

from typing import Any

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
    telephony_provider: str = "debug"
    call_control_id: str | None = None
    call_session_id: str | None = None
    call_leg_id: str | None = None
    twilio_voice_url_absolute: str = ""
    twilio_status_callback_url_absolute: str = ""
    twilio_gather_action_url_absolute: str = ""
    twilio_amd_answered_by: str | None = None
    twilio_voice_redirects: int = 0
    voice_gather_started: bool = False
    voicemail_message_played: bool = False
    webhook_event_types: list[str] = Field(default_factory=list)
    gather_result: dict[str, Any] = Field(default_factory=dict)
