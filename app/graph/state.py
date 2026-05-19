from typing import TypedDict

from app.core.enums import ConversationState, SessionOutcome
from app.schemas.transcript import TranscriptEntry


class GraphState(TypedDict, total=False):
    current_topic: int
    topic_one_complete: bool
    topic_two_complete: bool | None
    transcript: list[TranscriptEntry]
    turn_count: int
    current_state: str
    conversation_state: str
    latest_customer_message: str
    latest_agent_message: str
    agent_message: str
    next_state: str
    reasoning: str
    escalation_reason: str
    outcome: str
    resolution_note: str
    tools_to_call: list[str]


FINAL_STATES = {
    ConversationState.CLOSING.value,
    ConversationState.ESCALATING.value,
    ConversationState.VOICEMAIL.value,
}

FINAL_OUTCOMES = {
    ConversationState.CLOSING.value: SessionOutcome.RESOLVED.value,
    ConversationState.ESCALATING.value: SessionOutcome.ESCALATED.value,
    ConversationState.VOICEMAIL.value: SessionOutcome.NO_ANSWER.value,
}
