from __future__ import annotations

from app.llm.groq_client import GroqLLMClient
from app.schemas.parsed_intent import ParsedIntent


class OperatorInstructionParser:
    def __init__(self, llm_client: GroqLLMClient | None = None) -> None:
        self.llm_client = llm_client or GroqLLMClient()

    async def parse(self, instruction: str) -> ParsedIntent:
        prompt = (
            "Extract structured call intent from the operator instruction. "
            "Return strict JSON with keys: customer_id, issue_type, customer_name, phone_number, amount, due_date, "
            "reference_number, desired_resolution, raw_instruction, extracted_notes."
        )
        parsed = await self.llm_client.complete_json(prompt, instruction)
        parsed["raw_instruction"] = instruction
        return ParsedIntent.model_validate(parsed)
