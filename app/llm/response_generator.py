from __future__ import annotations

from app.core.enums import ConversationState
from app.llm.groq_client import GroqLLMClient
from app.schemas.parsed_intent import ParsedIntent
from app.schemas.transcript import TranscriptEntry


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
        system_prompt = (
            "You are a professional outbound voice agent. Keep replies concise, natural, and phone-friendly. "
            "Do not invent facts. Use only details from the parsed operator instruction and transcript. "
            "You must respond with a strict JSON object (no markdown, just JSON) containing:\n"
            '{\n  "next_state": "greeting | understanding | negotiating | confirming | closing | escalating | voicemail",\n'
            '  "reasoning": "brief explanation of why",\n'
            '  "resolution_note": "what was agreed if anything",\n'
            '  "tools_to_call": [{"name": "tool_name", "args": {"arg": "val"}}],\n'
            '  "agent_message": "what the agent should say next"\n}\n'
            "Available tools: log_payment_commitment(date, amount), resend_invoice(email), escalate_to_human(reason), log_dispute(reason), schedule_callback(date). "
            "Use the customer's latest message in context. "
            "Keywords hints: 'okay', 'next week' may indicate agreement; 'paid', 'wrong' may indicate dispute. But make the final decision holistically based on the transcript."
        )
        transcript_text = "\n".join(f"{entry.role}: {entry.content}" for entry in transcript[-6:])
        user_prompt = (
            f"Conversation state: {state.value}\n"
            f"Parsed intent: {intent.model_dump_json()}\n"
            f"Recent transcript:\n{transcript_text or 'None yet'}\n"
            f"Latest customer message: {customer_message or 'N/A'}\n"
            "Return the JSON decision."
        )
        return await self.llm_client.complete_json(system_prompt, user_prompt)
