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
        system_prompt = (
            "You are a professional outbound voice agent. Keep replies concise, natural, and phone-friendly. "
            "Do not invent facts. Use only details from the parsed operator instruction and transcript. "
            "If the state is escalating, explain that a human follow-up will happen. "
            "If the state is closing, end politely."
        )
        transcript_text = "\n".join(f"{entry.role}: {entry.content}" for entry in transcript[-6:])
        user_prompt = (
            f"Conversation state: {state.value}\n"
            f"Parsed intent: {intent.model_dump_json()}\n"
            f"Recent transcript:\n{transcript_text or 'None yet'}\n"
            f"Latest customer message: {customer_message or 'N/A'}\n"
            f"Escalation reason: {escalation_reason or 'N/A'}\n"
            "Generate the next single agent turn only."
        )
        return await self.llm_client.complete(system_prompt, user_prompt)
