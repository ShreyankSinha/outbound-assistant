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
        lowered = instruction.lower()
        amount_match = re.search(r"(\$\s*\d[\d,]*(?:\.\d{2})?)", instruction)
        desired_resolution = "understand the customer's situation and capture next steps"
        if "timeline" in lowered:
            desired_resolution = "understand the customer's plans and timeline"
        if any(word in lowered for word in ["invoice", "payment", "owe", "overdue"]):
            desired_resolution = "understand the customer's position and capture next steps"

        return {
            "customer_id": customer_id,
            "phone_number": phone_number,
            "call_objective": cleaned or "Call the customer",
            "topic_one": None,
            "topic_two": None,
            "single_topic": True,
            "issue_type": "project_follow_up" if "project" in lowered else "general_follow_up",
            "amount": amount_match.group(1).replace(" ", "") if amount_match else None,
            "desired_resolution": desired_resolution,
            "extracted_notes": [],
        }

