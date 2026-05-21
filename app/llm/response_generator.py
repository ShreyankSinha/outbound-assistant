from __future__ import annotations

import json
import logging

from app.llm.groq_client import GroqLLMClient
from app.llm.prompts import (
    OPENING_MESSAGE_PROMPT,
    SUMMARY_GENERATION_PROMPT,
    TURN_PLANNING_PROMPT,
)
from app.schemas.parsed_intent import ParsedIntent
from app.schemas.session_state import SessionState
from app.schemas.transcript import TranscriptEntry
from app.schemas.turn_plan import TurnPlan

logger = logging.getLogger(__name__)

_FALLBACK_PLAN_RESPONSE = "Thanks for that. Let me look into this and get back to you shortly."


class ResponseGenerator:
    def __init__(self, llm_client: GroqLLMClient | None = None) -> None:
        self.llm_client = llm_client or GroqLLMClient()

    async def plan_turn(
        self,
        call_objective: str,
        transcript: list[TranscriptEntry],
        session_state: SessionState,
    ) -> TurnPlan:
        """Single authoritative LLM call per customer turn.
        Includes one silent retry on malformed JSON. Returns a safe fallback TurnPlan on second failure.
        """
        user_prompt = (
            f"Call objective: {call_objective}\n"
            f"Customer commitment status: {session_state.customer_commitment_status}\n"
            f"Active blocker: {session_state.active_blocker_type or 'None'}\n"
            f"Transcript:\n{self._transcript_text(transcript[-8:])}"
        )

        for attempt in range(2):
            try:
                raw = await self.llm_client.complete_json(TURN_PLANNING_PROMPT, user_prompt)
                return TurnPlan.model_validate(raw)
            except Exception as exc:
                if attempt == 0:
                    logger.warning("plan_turn: attempt 1 failed (%s), retrying…", exc)
                else:
                    logger.error("plan_turn: both attempts failed (%s), using fallback.", exc)

        customer_turns = [e for e in transcript if e.role.lower() == "customer"]
        last = (customer_turns[-1].content.lower().strip() if customer_turns else "")
        farewell_words = {"bye", "goodbye", "thanks bye", "that's all", "no that's everything", "we're done"}
        if last in farewell_words:
            return TurnPlan(
                customer_intent="Customer is ending the call.",
                conversation_phase="closing",
                should_close=True,
                next_action="close_conversation",
                reasoning="Farewell detected in fallback path.",
                agent_response="Thanks for your time today. We'll be in touch. Goodbye.",
            )
        return TurnPlan(
            customer_intent="Customer intent unclear.",
            conversation_phase="gathering",
            next_action="gather_information",
            reasoning="LLM unavailable — using safe fallback.",
            agent_response=_FALLBACK_PLAN_RESPONSE,
        )

    async def generate_opening_message(self, intent: ParsedIntent) -> str:
        fallback = self._fallback_opening(intent)
        if not self.llm_client.client:
            return fallback
        user_prompt = (
            f"Operator instruction: {intent.raw_instruction or 'N/A'}\n"
            f"Call purpose / issue type: {intent.issue_type or 'N/A'}\n"
            f"Call objective: {intent.call_objective or 'N/A'}\n"
            f"Desired resolution: {intent.desired_resolution or 'N/A'}\n"
            f"Amount (if any): {getattr(intent, 'amount', None) or 'N/A'}\n"
        )
        raw = await self.llm_client.complete(OPENING_MESSAGE_PROMPT, user_prompt, prefer_fallback=True)
        return self._clean_spoken_response(raw, fallback)

    async def generate_summary(self, intent: ParsedIntent, transcript: list[TranscriptEntry]) -> str:
        fallback = self._fallback_summary(intent, transcript)
        if not self.llm_client.client:
            return fallback
        user_prompt = (
            f"Call objective: {intent.call_objective or 'N/A'}\n"
            f"Issue type: {intent.issue_type or 'N/A'}\n"
            f"Transcript:\n{self._transcript_text(transcript)}"
        )
        return await self.llm_client.complete(SUMMARY_GENERATION_PROMPT, user_prompt, prefer_fallback=True)

    @staticmethod
    def _transcript_text(transcript: list[TranscriptEntry]) -> str:
        return "\n".join(f"[{entry.role.upper()}] {entry.content}" for entry in transcript) or "No transcript yet."

    @staticmethod
    def _clean_spoken_response(raw: str, fallback: str) -> str:
        text = (raw or "").strip()
        if not text:
            return fallback

        text = text.replace("```", "").strip()
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        if not lines:
            return fallback

        meta_prefixes = (
            "here's",
            "here is",
            "natural closing",
            "closing message",
            "closing:",
            "opening message",
            "opening:",
            "spoken message",
            "agent message",
            "response:",
        )

        first_line = lines[0].lower()
        if first_line.startswith(meta_prefixes):
            lines = lines[1:]
        elif ":" in lines[0]:
            prefix, remainder = lines[0].split(":", maxsplit=1)
            if prefix.strip().lower() in {
                "closing",
                "closing message",
                "opening",
                "opening message",
                "agent message",
                "response",
            }:
                lines[0] = remainder.strip()

        cleaned = " ".join(line for line in lines if line).strip().strip("\"'")
        return cleaned or fallback

    @staticmethod
    def _fallback_opening(intent: ParsedIntent) -> str:
        context = (
            intent.call_objective
            or intent.desired_resolution
            or intent.issue_type
            or "your account"
        ).rstrip(".").replace("_", " ")
        return (
            f"Hi, my name is Alex from iSoft. I'm calling today regarding {context} — "
            f"I was hoping to have a quick chat if you have a moment."
        )

    @staticmethod
    def _fallback_summary(intent: ParsedIntent, transcript: list[TranscriptEntry]) -> str:
        customer_statements = [entry.content for entry in transcript if entry.role.lower() == "customer"]
        objective = intent.call_objective or intent.issue_type or "the call objective"
        if not customer_statements:
            return (
                f"The call focused on {objective}. "
                "The customer did not provide much detail before the call ended."
            )
        customer_context = f"The customer explained that {customer_statements[-1].rstrip('.')}."
        return (
            f"The call focused on {objective}. {customer_context} "
            "Alex captured the response and closed the conversation politely."
        )
