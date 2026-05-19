from __future__ import annotations

from app.core.enums import ConversationState
from app.graph.state import GraphState
from app.llm.response_generator import ResponseGenerator
from app.schemas.parsed_intent import ParsedIntent


async def agent_node(
    state: GraphState,
    intent: ParsedIntent,
    responder: ResponseGenerator | None = None,
) -> GraphState:
    generator = responder or ResponseGenerator()
    transcript = state.get("transcript", [])
    current_topic = state.get("current_topic", 1)
    topic_one_complete = state.get("topic_one_complete", False)
    topic_two_complete = state.get("topic_two_complete", None if intent.single_topic else False)
    customer_message = (state.get("latest_customer_message") or "").strip()
    warning_note = _transcript_warning(transcript)

    if not customer_message:
        opening = await generator.generate_opening_message(intent)
        return {
            "next_state": ConversationState.UNDERSTANDING.value,
            "conversation_state": ConversationState.UNDERSTANDING.value,
            "agent_message": opening,
            "latest_agent_message": opening,
            "current_topic": 1,
            "topic_one_complete": False,
            "topic_two_complete": None if intent.single_topic else False,
            "reasoning": "Opening the call and introducing the first topic.",
            "resolution_note": warning_note or "",
            "tools_to_call": [],
        }

    if current_topic == 1 and not topic_one_complete:
        transition = await generator.judge_topic_transition(intent, transcript)
        reasoning = str(transition.get("reasoning") or "Continuing topic one.")
        if bool(transition.get("topic_one_complete")):
            topic_one_complete = True
            if intent.single_topic or not intent.topic_two:
                closing = await generator.generate_closing_message(intent, transcript)
                return {
                    "next_state": ConversationState.CLOSING.value,
                    "conversation_state": ConversationState.CLOSING.value,
                    "agent_message": closing,
                    "latest_agent_message": closing,
                    "current_topic": 1,
                    "topic_one_complete": True,
                    "topic_two_complete": None,
                    "reasoning": reasoning,
                    "resolution_note": _combine_notes(reasoning, warning_note),
                    "tools_to_call": [],
                }

            bridge = await generator.generate_topic_transition_message(intent, transcript)
            return {
                "next_state": "topic_two",
                "conversation_state": ConversationState.NEGOTIATING.value,
                "agent_message": bridge,
                "latest_agent_message": bridge,
                "current_topic": 2,
                "topic_one_complete": True,
                "topic_two_complete": False,
                "reasoning": reasoning,
                "resolution_note": _combine_notes(reasoning, warning_note),
                "tools_to_call": [],
            }

        follow_up = await generator.generate_topic_follow_up(intent, transcript, 1)
        return {
            "next_state": "topic_one",
            "conversation_state": ConversationState.UNDERSTANDING.value,
            "agent_message": follow_up,
            "latest_agent_message": follow_up,
            "current_topic": 1,
            "topic_one_complete": False,
            "topic_two_complete": topic_two_complete,
            "reasoning": reasoning,
            "resolution_note": warning_note or "",
            "tools_to_call": [],
        }

    if current_topic == 2 and topic_two_complete is False:
        closing = await generator.generate_closing_message(intent, transcript)
        reasoning = "Topic two was discussed, so the call can close naturally."
        return {
            "next_state": ConversationState.CLOSING.value,
            "conversation_state": ConversationState.CLOSING.value,
            "agent_message": closing,
            "latest_agent_message": closing,
            "current_topic": 2,
            "topic_one_complete": True,
            "topic_two_complete": True,
            "reasoning": reasoning,
            "resolution_note": warning_note or "",
            "tools_to_call": [],
        }

    closing = await generator.generate_closing_message(intent, transcript)
    return {
        "next_state": ConversationState.CLOSING.value,
        "conversation_state": ConversationState.CLOSING.value,
        "agent_message": closing,
        "latest_agent_message": closing,
        "current_topic": current_topic,
        "topic_one_complete": topic_one_complete,
        "topic_two_complete": topic_two_complete,
        "reasoning": "The conversation has reached a natural close.",
        "resolution_note": warning_note or "",
        "tools_to_call": [],
    }

def greeting_node(state: GraphState, intent: ParsedIntent) -> GraphState:
    return {
        "conversation_state": ConversationState.UNDERSTANDING.value,
        "latest_agent_message": f"Hi, this is Alex from iSoft calling about {intent.topic_one.rstrip('.')}.",
    }


def understanding_node(state: GraphState, intent: ParsedIntent) -> GraphState:
    return {
        "conversation_state": ConversationState.UNDERSTANDING.value,
        "latest_agent_message": f"Could you tell me a little more about {intent.topic_one.rstrip('.')}?",
    }


def negotiating_node(state: GraphState, intent: ParsedIntent) -> GraphState:
    return {
        "conversation_state": ConversationState.NEGOTIATING.value,
        "latest_agent_message": (
            f"Thanks. I'd also like to ask about {(intent.topic_two or intent.topic_one).rstrip('.')}."
        ),
    }


def confirming_node(state: GraphState, intent: ParsedIntent) -> GraphState:
    return {
        "conversation_state": ConversationState.CLOSING.value,
        "latest_agent_message": "Thanks for talking through that with me. I'll note it down and let you go.",
    }


def closing_node(state: GraphState, intent: ParsedIntent) -> GraphState:
    return {
        "conversation_state": ConversationState.CLOSING.value,
        "latest_agent_message": "Thank you for your time today. Goodbye.",
    }


def escalating_node(state: GraphState, intent: ParsedIntent) -> GraphState:
    return {
        "conversation_state": ConversationState.ESCALATING.value,
        "latest_agent_message": "I'll hand this over to a human teammate for follow-up.",
    }


def voicemail_node(state: GraphState, intent: ParsedIntent) -> GraphState:
    return {
        "conversation_state": ConversationState.VOICEMAIL.value,
        "latest_agent_message": "Hi, this is Alex from iSoft. Please call us back when you have a moment. Thank you.",
    }


def _transcript_warning(transcript: list[object]) -> str | None:
    char_count = sum(len(getattr(entry, "content", "")) for entry in transcript)
    if len(transcript) > 20 or char_count > 10000:
        return "[TRANSCRIPT WARNING] Transcript exceeded 20 turns or 10,000 characters."
    return None


def _combine_notes(*notes: str | None) -> str:
    return " ".join(note for note in notes if note).strip()
