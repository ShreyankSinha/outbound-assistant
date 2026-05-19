from __future__ import annotations

import re

from app.llm.groq_client import GroqLLMClient
from app.llm.prompts import INSTRUCTION_PARSE_PROMPT
from app.schemas.parsed_intent import ParsedIntent
from app.services.customer_lookup import get_phone_by_id


class OperatorInstructionParser:
    def __init__(self, llm_client: GroqLLMClient | None = None) -> None:
        self.llm_client = llm_client or GroqLLMClient()

    async def parse(self, instruction: str) -> ParsedIntent:
        customer_id = self._extract_customer_id(instruction)
        phone_number = None
        if customer_id is not None:
            try:
                phone_number = get_phone_by_id(customer_id)
            except (LookupError, FileNotFoundError, ValueError):
                phone_number = None
        fallback_payload = self._fallback_parse_instruction(instruction, customer_id, phone_number)
        user_prompt = (
            f"Operator instruction: {instruction}\n"
            f"Known customer_id: {customer_id}\n"
            f"Resolved phone_number: {phone_number}\n"
        )
        parsed: dict[str, object] = {}
        if self.llm_client.client:
            try:
                parsed = await self.llm_client.complete_json(INSTRUCTION_PARSE_PROMPT, user_prompt)
            except Exception:
                parsed = {}

        normalized = {
            **fallback_payload,
            **{key: value for key, value in parsed.items() if value not in (None, "", [])},
            "customer_id": customer_id,
            "phone_number": phone_number,
            "raw_instruction": instruction,
        }
        return ParsedIntent.model_validate(normalized)

    @staticmethod
    def _extract_customer_id(instruction: str) -> int | None:
        match = re.search(r"customer\s*id[:\s#-]*(\d+)", instruction, re.IGNORECASE)
        return int(match.group(1)) if match else None

    def _fallback_parse_instruction(
        self,
        instruction: str,
        customer_id: int | None,
        phone_number: str | None,
    ) -> dict[str, object]:
        cleaned = re.sub(r"customer\s*id[:\s#-]*\d+\s*,?\s*", "", instruction, flags=re.IGNORECASE).strip()
        cleaned = cleaned.rstrip(".")
        first_topic, second_topic = self._split_topics(cleaned)
        lowered = instruction.lower()
        if "customer's plans" in lowered and "project" in lowered:
            first_topic = "Find out what the customer's plans are for the project they are working on"
        if "timeline" in lowered and second_topic:
            second_topic = "the timeline"
        amount_match = re.search(r"(\$\s*\d[\d,]*(?:\.\d{2})?)", instruction)
        desired_resolution = "understand the customer's situation and capture next steps"
        if "timeline" in lowered:
            desired_resolution = "understand the customer's plans and timeline"
        if any(word in lowered for word in ["invoice", "payment", "owe", "overdue"]):
            desired_resolution = "understand the customer's position and capture next steps"

        return {
            "customer_id": customer_id,
            "phone_number": phone_number,
            "topic_one": first_topic,
            "topic_two": second_topic,
            "single_topic": second_topic is None,
            "issue_type": "project_follow_up" if "project" in lowered else "general_follow_up",
            "amount": amount_match.group(1).replace(" ", "") if amount_match else None,
            "desired_resolution": desired_resolution,
            "extracted_notes": [],
        }

    @staticmethod
    def _split_topics(cleaned_instruction: str) -> tuple[str, str | None]:
        if not cleaned_instruction:
            return "understand the customer's situation", None

        normalized = re.sub(r"\s+", " ", cleaned_instruction).strip(" ,.")
        split_patterns = [
            r"\s+and\s+get\s+a\s+sense\s+of\s+",
            r"\s+and\s+find\s+out\s+",
            r"\s+and\s+ask\s+about\s+",
            r"\s+and\s+discuss\s+",
            r"\s+also\s+",
            r"\s+as well as\s+",
        ]
        for pattern in split_patterns:
            parts = re.split(pattern, normalized, maxsplit=1, flags=re.IGNORECASE)
            if len(parts) == 2:
                first = parts[0].strip(" ,.")
                second = parts[1].strip(" ,.")
                if second and not second.lower().startswith("the "):
                    second = second[0].upper() + second[1:]
                return first, second or None

        sentence_parts = [part.strip(" ,.") for part in re.split(r"[.;]", normalized) if part.strip(" ,.")]
        if len(sentence_parts) >= 2:
            return sentence_parts[0], sentence_parts[1]
        return normalized, None
