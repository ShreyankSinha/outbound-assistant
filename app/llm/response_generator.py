from __future__ import annotations

from app.core.enums import ConversationState
from app.llm.groq_client import GroqLLMClient
from app.llm.prompts import (
    CLOSING_PROMPT,
    OPENING_MESSAGE_PROMPT,
    SUMMARY_GENERATION_PROMPT,
    TOPIC_FOLLOW_UP_PROMPT,
    TOPIC_TRANSITION_PROMPT,
)
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
        if state == ConversationState.GREETING:
            return await self.generate_opening_message(intent)
        if state == ConversationState.CLOSING:
            return await self.generate_closing_message(intent, transcript)
        if state == ConversationState.ESCALATING:
            return "Thanks for explaining that. I'll hand this over for a human follow-up from our team."
        if state == ConversationState.VOICEMAIL:
            return "Hi, this is Alex from iSoft calling to follow up. Please call us back when you have a moment. Thank you."
        topic_number = 2 if "timeline" in customer_message.lower() else 1
        return await self.generate_topic_follow_up(intent, transcript, topic_number)

    async def generate_opening_message(self, intent: ParsedIntent) -> str:
        fallback = self._fallback_opening(intent)
        if not self.llm_client.client:
            return fallback
        user_prompt = (
            f"Topic one: {intent.topic_one}\n"
            f"Topic two: {intent.topic_two or 'N/A'}\n"
            f"Single topic: {intent.single_topic}"
        )
        raw = await self.llm_client.complete(OPENING_MESSAGE_PROMPT, user_prompt, prefer_fallback=True)
        return self._clean_spoken_response(raw, fallback)

    async def judge_topic_transition(self, intent: ParsedIntent, transcript: list[TranscriptEntry]) -> dict[str, object]:
        if not self.llm_client.client:
            return self._fallback_transition_judgment(transcript)
        user_prompt = (
            f"Topic one: {intent.topic_one}\n"
            f"Topic two: {intent.topic_two or 'N/A'}\n"
            f"Transcript:\n{self._transcript_text(transcript)}"
        )
        try:
            result = await self.llm_client.complete_json(TOPIC_TRANSITION_PROMPT, user_prompt)
        except Exception:
            result = self._fallback_transition_judgment(transcript)
        return {
            "topic_one_complete": bool(result.get("topic_one_complete")),
            "reasoning": str(result.get("reasoning") or "Topic one needs a little more discussion."),
        }

    async def generate_topic_transition_message(self, intent: ParsedIntent, transcript: list[TranscriptEntry]) -> str:
        if intent.single_topic or not intent.topic_two:
            return await self.generate_closing_message(intent, transcript)
        return (
            f"Thanks, that helps. Before we wrap up, I'd also like to ask about {intent.topic_two.rstrip('.')}."
        )

    async def generate_topic_follow_up(
        self,
        intent: ParsedIntent,
        transcript: list[TranscriptEntry],
        topic_number: int,
        customer_message: str = "",
    ) -> str:
        topic = intent.topic_one if topic_number == 1 else (intent.topic_two or intent.topic_one)
        fallback = self._fallback_topic_follow_up(topic, customer_message, topic_number)
        if not self.llm_client.client:
            return fallback

        user_prompt = (
            f"Current topic number: {topic_number}\n"
            f"Current topic label: {topic}\n"
            f"Topic one: {intent.topic_one}\n"
            f"Topic two: {intent.topic_two or 'N/A'}\n"
            f"Latest customer message: {customer_message or 'N/A'}\n"
            f"Transcript:\n{self._transcript_text(transcript)}"
        )
        raw = await self.llm_client.complete(TOPIC_FOLLOW_UP_PROMPT, user_prompt, prefer_fallback=True)
        return self._clean_spoken_response(raw, fallback)

    async def generate_closing_message(self, intent: ParsedIntent, transcript: list[TranscriptEntry]) -> str:
        fallback = "Thanks for your time today. That covers everything I needed, so I'll let you go. Goodbye."
        if not self.llm_client.client:
            return fallback
        user_prompt = (
            f"Topic one: {intent.topic_one}\n"
            f"Topic two: {intent.topic_two or 'N/A'}\n"
            f"Transcript:\n{self._transcript_text(transcript)}"
        )
        raw = await self.llm_client.complete(CLOSING_PROMPT, user_prompt, prefer_fallback=True)
        return self._clean_spoken_response(raw, fallback)

    async def generate_summary(self, intent: ParsedIntent, transcript: list[TranscriptEntry]) -> str:
        fallback = self._fallback_summary(intent, transcript)
        if not self.llm_client.client:
            return fallback
        user_prompt = (
            f"Topic one: {intent.topic_one}\n"
            f"Topic two: {intent.topic_two or 'N/A'}\n"
            f"Single topic: {intent.single_topic}\n"
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
        if intent.single_topic or not intent.topic_two:
            return (
                f"Hi, this is Alex calling on behalf of iSoft. I was hoping to ask you a few questions about "
                f"{intent.topic_one.rstrip('.')} if you have a moment."
            )
        return (
            f"Hi, this is Alex calling on behalf of iSoft. I was hoping to ask you a few questions about "
            f"{intent.topic_one.rstrip('.')} and get a sense of {intent.topic_two.rstrip('.').lower()} if you have a moment."
        )

    @staticmethod
    def _fallback_topic_follow_up(topic: str, customer_message: str, topic_number: int) -> str:
        if topic_number == 1:
            if customer_message:
                return f"Thanks, that helps. What else can you tell me about {topic.rstrip('.')}?"
            return f"Thanks. Could you tell me a little more about {topic.rstrip('.')}?"
        if customer_message:
            return f"That makes sense. What more can you share about {topic.rstrip('.')}?"
        if topic_number == 1:
            return f"Thanks. Could you tell me a little more about {topic.rstrip('.')}?"
        return f"That makes sense. What can you share about {topic.rstrip('.')}?"

    @staticmethod
    def _fallback_transition_judgment(transcript: list[TranscriptEntry]) -> dict[str, object]:
        customer_turns = [entry for entry in transcript if entry.role.lower() == "customer"]
        last_customer = customer_turns[-1].content.lower() if customer_turns else ""
        complete = len(customer_turns) >= 2 or any(
            phrase in last_customer
            for phrase in ["we're", "we are", "plan", "timeline", "next", "by", "around", "should be", "expect"]
        )
        reasoning = "The customer has given enough context on topic one to move forward." if complete else (
            "The customer has not given enough detail on topic one yet."
        )
        return {"topic_one_complete": complete, "reasoning": reasoning}

    @staticmethod
    def _fallback_summary(intent: ParsedIntent, transcript: list[TranscriptEntry]) -> str:
        customer_statements = [entry.content for entry in transcript if entry.role.lower() == "customer"]
        if not customer_statements:
            customer_context = "The customer did not provide much detail during the call."
        else:
            customer_context = f"The customer explained that {customer_statements[-1].rstrip('.') }."
        if intent.single_topic or not intent.topic_two:
            return (
                f"The call focused on {intent.topic_one}. {customer_context} "
                "Alex captured the response and closed the conversation politely."
            )
        return (
            f"The call first covered {intent.topic_one}, then moved to {intent.topic_two}. "
            f"{customer_context} Alex captured the customer's answers across both topics and closed the call politely."
        )
