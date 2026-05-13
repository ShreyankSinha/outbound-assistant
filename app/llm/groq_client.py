from __future__ import annotations

import json
import re
from typing import Any

from groq import AsyncGroq

from app.config import get_settings


class GroqLLMClient:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.client = AsyncGroq(api_key=self.settings.groq_api_key) if self.settings.groq_api_key else None

    async def complete(self, system_prompt: str, user_prompt: str, prefer_fallback: bool = False) -> str:
        if not self.client:
            return self._fallback_text(user_prompt)

        model = self.settings.groq_model_fallback if prefer_fallback else self.settings.groq_model_primary
        try:
            response = await self.client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.2,
            )
            return response.choices[0].message.content or ""
        except Exception:
            if prefer_fallback:
                return self._fallback_text(user_prompt)
            return await self.complete(system_prompt, user_prompt, prefer_fallback=True)

    async def complete_json(self, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        text = await self.complete(system_prompt, user_prompt)
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return self._fallback_parse(user_prompt)

    def _fallback_text(self, user_prompt: str) -> str:
        prompt = user_prompt.lower()
        if "conversation state: greeting" in prompt:
            return "Hello, this is the accounts assistant calling. Is now a good time to speak briefly?"
        if "conversation state: understanding" in prompt:
            return "I'm calling about an outstanding matter on your account, and I'd like to explain the reason for the call."
        if "conversation state: negotiating" in prompt:
            if "callback" in prompt:
                return "Certainly. We can arrange a callback. What time would suit you best?"
            return "Could you let me know whether you're able to resolve this today or if you'd prefer to arrange a payment date?"
        if "conversation state: confirming" in prompt:
            return "Thank you. I've noted the arrangement discussed, and we'll update the account accordingly. Goodbye."
        if "conversation state: escalating" in prompt:
            return "Thanks for explaining that. I'll escalate this to a human agent for follow-up."
        if "conversation state: closing" in prompt:
            return "Thank you for your time today. Goodbye."
        if "conversation state: voicemail" in prompt:
            return "Hello, this is a brief follow-up call regarding an outstanding matter. Please call us back when convenient. Thank you."
        return "Thanks for taking the call. I'm following up regarding your outstanding matter. Could you let me know the best way to resolve this today?"

    def _fallback_parse(self, instruction: str) -> dict[str, Any]:
        customer_id_match = re.search(r"customer\s*id\s*(\d+)", instruction, re.IGNORECASE)
        currency_match = re.search(r"(\$\s*\d[\d,]*(?:\.\d{2})?)", instruction)
        amount_match = currency_match or re.search(r"owes?\s+(\d[\d,]*(?:\.\d{2})?)", instruction, re.IGNORECASE)
        due_date_match = re.search(r"\b(?:from|on|due)\s+([A-Za-z0-9 ]{3,25})", instruction, re.IGNORECASE)
        name_match = re.search(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\b", instruction)
        lowered = instruction.lower()
        issue_type = "unpaid_invoice" if any(word in lowered for word in ["invoice", "paid", "owes", "overdue"]) else "general_follow_up"
        resolution = "seek payment commitment" if any(word in lowered for word in ["commitment", "pay", "owes"]) else "clarify and resolve"
        return {
            "customer_id": int(customer_id_match.group(1)) if customer_id_match else None,
            "issue_type": issue_type,
            "customer_name": name_match.group(1) if name_match else None,
            "phone_number": None,
            "amount": amount_match.group(1).replace(" ", "").rstrip(".,") if amount_match else None,
            "due_date": due_date_match.group(1).strip() if due_date_match else None,
            "reference_number": None,
            "desired_resolution": resolution,
            "raw_instruction": instruction,
            "extracted_notes": [],
        }
