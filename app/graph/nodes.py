from __future__ import annotations

from app.core.enums import ConversationState
from app.graph.state import GraphState
from app.schemas.parsed_intent import ParsedIntent


def greeting_node(state: GraphState, intent: ParsedIntent) -> GraphState:
    customer_name = intent.customer_name or "there"
    return {
        "conversation_state": ConversationState.UNDERSTANDING.value,
        "latest_agent_message": (
            f"Hello, this is the accounts assistant calling for {customer_name}. "
            "Is now a good time to speak briefly?"
        ),
    }


def understanding_node(state: GraphState, intent: ParsedIntent) -> GraphState:
    issue = intent.issue_type.replace("_", " ")
    amount = f" for {intent.amount}" if intent.amount else ""
    return {
        "conversation_state": ConversationState.NEGOTIATING.value,
        "latest_agent_message": (
            f"I'm calling about the {issue}{amount}. "
            f"My goal today is to {intent.desired_resolution}."
        ),
    }


def negotiating_node(state: GraphState, intent: ParsedIntent) -> GraphState:
    message = (state.get("latest_customer_message") or "").lower()
    if "human" in message or "person" in message:
        return {
            "conversation_state": ConversationState.ESCALATING.value,
            "latest_agent_message": "I can arrange a handoff to a human agent now.",
            "escalation_reason": "customer_requested_human",
        }
    if any(word in message for word in ["voicemail", "beep"]):
        return {
            "conversation_state": ConversationState.VOICEMAIL.value,
            "latest_agent_message": "Hello, please call us back when convenient regarding your outstanding matter. Thank you.",
        }
    if any(word in message for word in ["yes", "pay", "tomorrow", "today", "arrange", "callback"]):
        return {
            "conversation_state": ConversationState.CONFIRMING.value,
            "latest_agent_message": "Thank you. Let me confirm the arrangement we've discussed.",
            "resolution_note": state.get("latest_customer_message", ""),
        }
    if any(word in message for word in ["dispute", "wrong", "don't owe", "not mine"]):
        return {
            "conversation_state": ConversationState.ESCALATING.value,
            "latest_agent_message": "Thanks for explaining that. I'll escalate this for review by a human agent.",
            "escalation_reason": "customer_disputed_issue",
        }
    return {
        "conversation_state": ConversationState.NEGOTIATING.value,
        "latest_agent_message": (
            "I understand. Could you tell me whether you'd prefer to resolve it today, "
            "set a payment date, or have someone call you back?"
        ),
    }


def confirming_node(state: GraphState, intent: ParsedIntent) -> GraphState:
    return {
        "conversation_state": ConversationState.CLOSING.value,
        "latest_agent_message": (
            f"To confirm, the outcome is: {state.get('resolution_note') or 'a follow-up arrangement was made'}. "
            "We'll note that on the account. Thank you for your time today. Goodbye."
        ),
    }


def closing_node(state: GraphState, intent: ParsedIntent) -> GraphState:
    return {
        "conversation_state": ConversationState.CLOSING.value,
        "latest_agent_message": "Thank you for your time today. Goodbye.",
    }


def escalating_node(state: GraphState, intent: ParsedIntent) -> GraphState:
    return {
        "conversation_state": ConversationState.ESCALATING.value,
        "latest_agent_message": "I'm escalating this interaction to a human agent for follow-up.",
    }


def voicemail_node(state: GraphState, intent: ParsedIntent) -> GraphState:
    return {
        "conversation_state": ConversationState.VOICEMAIL.value,
        "latest_agent_message": "Hello, please call us back when you have a moment. Thank you.",
    }
