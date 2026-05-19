from __future__ import annotations

from app.core.enums import ConversationState
from app.graph.state import GraphState
from app.schemas.parsed_intent import ParsedIntent


from app.llm.response_generator import ResponseGenerator
from app.schemas.transcript import TranscriptEntry

async def agent_node(state: GraphState, intent: ParsedIntent) -> GraphState:
    llm = ResponseGenerator()
    current_state_val = state.get("current_state") or ConversationState.GREETING.value
    current_state = ConversationState(current_state_val)
    customer_message = state.get("latest_customer_message", "")
    
    transcript_dicts = state.get("transcript", [])
    transcript = [TranscriptEntry(**t) for t in transcript_dicts]

    decision = await llm.generate_decision(
        state=current_state,
        intent=intent,
        transcript=transcript,
        customer_message=customer_message,
    )

    next_state_val = decision.get("next_state", current_state.value)
    
    # Ensure next_state is a valid ConversationState
    try:
        ConversationState(next_state_val)
    except ValueError:
        next_state_val = current_state.value

    resolution_note = decision.get("resolution_note", "")
    
    # Transcript growth logging
    turn_count = len(transcript)
    char_count = sum(len(t.content) for t in transcript if t.content)
    if turn_count > 20 or char_count > 10000:
        warning = f"Warning: Transcript exceeded limits (turns={turn_count}, chars={char_count})."
        resolution_note = f"{warning} {resolution_note}".strip()

    return {
        "conversation_state": next_state_val,
        "latest_agent_message": decision.get("agent_message", ""),
        "resolution_note": resolution_note,
        "tools_to_call": decision.get("tools_to_call", []),
    }

