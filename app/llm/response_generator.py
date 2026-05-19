from __future__ import annotations

from app.core.enums import ConversationState
from app.llm.groq_client import GroqLLMClient
from app.schemas.parsed_intent import ParsedIntent
from app.schemas.transcript import TranscriptEntry
from app.llm.prompts import DECISION_SYSTEM_PROMPT


class ResponseGenerator:
    def __init__(self, llm_client: GroqLLMClient | None = None) -> None:
        self.llm_client = llm_client or GroqLLMClient()

    async def generate(
        self,
        state: ConversationState,
        intent: ParsedIntent,
        transcript: list[TranscriptEntry],
        customer_message: str = "",
        escalation_reason: str | None = None,
    ) -> str:
        decision = await self.generate_decision(state, intent, transcript, customer_message)
        return decision.get("agent_message", "Hello.")

    async def generate_decision(
        self,
        state: ConversationState,
        intent: ParsedIntent,
        transcript: list[TranscriptEntry],
        customer_message: str = "",
    ) -> dict:
        transcript_text = "\n".join(f"{entry.role}: {entry.content}" for entry in transcript[-6:])
        user_prompt = (
            f"Conversation state: {state.value}\n"
            f"Parsed intent: {intent.model_dump_json()}\n"
            f"Recent transcript:\n{transcript_text or 'None yet'}\n"
            f"Latest customer message: {customer_message or 'N/A'}\n"
            "Return the JSON decision."
        )
        
        valid_states = {"greeting", "understanding", "negotiating", "confirming", "closing", "escalating", "voicemail"}
        
        # We will use complete() and parse manually so we have the raw response to log.
        for attempt in range(2):
            raw_response = await self.llm_client.complete(DECISION_SYSTEM_PROMPT, user_prompt)
            try:
                import json
                decision = json.loads(raw_response)
                next_state = decision.get("next_state")
                agent_message = decision.get("agent_message")
                
                if next_state in valid_states and agent_message:
                    return decision
            except Exception:
                pass
                
        # If it fails twice, return fallback
        turn_number = len(transcript)
        fallback_note = f"LLM parsing failed. state={state.value}, turn={turn_number}. Raw response: {raw_response}"
        return {
            "next_state": state.value,
            "agent_message": "Sorry, give me one moment while I check that for you.",
            "tools_to_call": [],
            "reasoning": "fallback: LLM response was malformed after 1 retry",
            "resolution_note": fallback_note
        }
