from __future__ import annotations

from app.llm.groq_client import GroqLLMClient
from app.schemas.parsed_intent import ParsedIntent
from app.llm.prompts import INTENT_EXTRACTION_PROMPT


class OperatorInstructionParser:
    def __init__(self, llm_client: GroqLLMClient | None = None) -> None:
        self.llm_client = llm_client or GroqLLMClient()

    async def parse(self, instruction: str) -> ParsedIntent:
        parsed = await self.llm_client.complete_json(INTENT_EXTRACTION_PROMPT, instruction)
        parsed["raw_instruction"] = instruction
        return ParsedIntent.model_validate(parsed)
