from typing import TypedDict

from app.core.enums import ConversationState, SessionOutcome


class GraphState(TypedDict, total=False):
    current_state: str
    conversation_state: str
    latest_customer_message: str
    latest_agent_message: str
    escalation_reason: str
    outcome: str
    resolution_note: str
    transcript: list[dict]
    tools_to_call: list[dict]


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
