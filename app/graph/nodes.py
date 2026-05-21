from __future__ import annotations

from app.core.enums import ConversationState, SessionOutcome
from app.graph.state import GraphState
from app.llm.response_generator import ResponseGenerator
from app.schemas.parsed_intent import ParsedIntent
from app.schemas.session_state import SessionState


async def agent_node(
    state: GraphState,
    intent: ParsedIntent,
    responder: ResponseGenerator | None = None,
    session: SessionState | None = None,
) -> GraphState:
    generator = responder or ResponseGenerator()
    transcript = state.get("transcript", [])
    customer_message = (state.get("latest_customer_message") or "").strip()
    warning_note = _transcript_warning(transcript)

    # ── Opening: no customer message yet ──────────────────────────────────────
    if not customer_message:
        opening = await generator.generate_opening_message(intent)
        return {
            "next_state": ConversationState.UNDERSTANDING.value,
            "conversation_state": ConversationState.UNDERSTANDING.value,
            "agent_message": opening,
            "latest_agent_message": opening,
            "next_action": "gather_information",
            "objective_met": False,
            "reasoning": "Opening the call.",
            "resolution_note": warning_note or "",
            "tools_to_call": [],
        }

    # ── Call already ended: no-op ─────────────────────────────────────────────
    call_ended = state.get("conversation_state") in (
        ConversationState.CLOSING.value,
        ConversationState.ESCALATING.value,
        ConversationState.VOICEMAIL.value,
    )
    if call_ended:
        return {}

    # ── Single planning call ──────────────────────────────────────────────────
    call_objective = (
        intent.call_objective
        or (session.call_objective if session else "")
        or intent.raw_instruction
        or "Complete the call."
    )

    # Build a minimal SessionState snapshot for plan_turn context if not provided
    if session is None:
        from app.schemas.session_state import SessionState as _SS
        session = _SS(
            session_id="inline",
            timestamp_start="",
            operator_instruction=intent.raw_instruction or "",
            parsed_intent=intent,
            call_objective=call_objective,
            customer_commitment_status=state.get("customer_commitment_status", "none"),
            active_blocker_type=state.get("active_blocker_type"),
        )

    plan = await generator.plan_turn(call_objective, transcript, session)
    plan_dict = plan.model_dump()

    # ── Map TurnPlan → GraphState ─────────────────────────────────────────────
    updates: GraphState = {
        "agent_message": plan.agent_response,
        "latest_agent_message": plan.agent_response,
        "next_action": plan.next_action,
        "objective_met": plan.objective_met,
        "customer_intent": plan.customer_intent,
        "reasoning": plan.reasoning,
        "resolution_note": warning_note or "",
        "tools_to_call": [],
    }

    if plan.active_blocker:
        updates["active_blocker_type"] = plan.active_blocker.type
        updates["active_blocker_details"] = plan.active_blocker.details

    if plan.customer_commitment:
        updates["customer_commitment_status"] = plan.customer_commitment.status
        updates["customer_commitment_timeline"] = plan.customer_commitment.timeline
        updates["customer_commitment_details"] = plan.customer_commitment.details

    if plan.should_escalate:
        updates["conversation_state"] = ConversationState.ESCALATING.value
        updates["next_state"] = ConversationState.ESCALATING.value
        updates["escalation_reason"] = plan.escalation_reason or "Customer requested human."
        updates["outcome"] = SessionOutcome.ESCALATED.value
    elif plan.should_close or plan.objective_met:
        updates["conversation_state"] = ConversationState.CLOSING.value
        updates["next_state"] = ConversationState.CLOSING.value
        updates["outcome"] = SessionOutcome.RESOLVED.value
    else:
        updates["conversation_state"] = ConversationState.UNDERSTANDING.value
        updates["next_state"] = ConversationState.UNDERSTANDING.value

    # Append serialised TurnPlan for logging
    existing_plans = list(state.get("turn_plans") or [])
    existing_plans.append(plan_dict)
    updates["turn_plans"] = existing_plans

    return updates


def greeting_node(state: GraphState, intent: ParsedIntent) -> GraphState:
    return {
        "conversation_state": ConversationState.UNDERSTANDING.value,
        "latest_agent_message": ResponseGenerator._fallback_opening(intent),
    }


def understanding_node(state: GraphState, intent: ParsedIntent) -> GraphState:
    return {
        "conversation_state": ConversationState.UNDERSTANDING.value,
        "latest_agent_message": (
            f"Could you tell me a little more about {(intent.call_objective or 'your situation').rstrip('.')}?"
        ),
    }


def negotiating_node(state: GraphState, intent: ParsedIntent) -> GraphState:
    return {
        "conversation_state": ConversationState.UNDERSTANDING.value,
        "latest_agent_message": "Thanks for that — let me look into the best way to help you.",
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


def _customer_turns(transcript: list[object]) -> list[object]:
    return [entry for entry in transcript if getattr(entry, "role", "").lower() == "customer"]


def _is_meaningful_customer_response(message: str) -> bool:
    lowered = message.lower().strip()
    non_answers = {
        "", "yeah", "yes", "yep", "okay", "ok", "fine", "sure",
        "and", "and?", "bye", "goodbye", "now is fine",
        "yeah now is fine", "yes now is fine", "that's fine", "thats fine",
    }
    return lowered not in non_answers and len(lowered.split()) >= 4
