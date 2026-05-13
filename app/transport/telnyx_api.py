from __future__ import annotations

import base64
import json
from urllib.parse import urljoin

import httpx

from app.config import get_settings


class TelnyxCallControlClient:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.base_url = "https://api.telnyx.com/v2"

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.settings.telnyx_api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def build_webhook_url(self) -> str:
        base = self.settings.telnyx_public_webhook_base_url.rstrip("/") + "/"
        return urljoin(base, "webhooks/telnyx")

    @staticmethod
    def encode_client_state(payload: dict[str, str]) -> str:
        return base64.b64encode(json.dumps(payload).encode("utf-8")).decode("utf-8")

    @staticmethod
    def decode_client_state(client_state: str | None) -> dict[str, str]:
        if not client_state:
            return {}
        try:
            decoded = base64.b64decode(client_state).decode("utf-8")
            return json.loads(decoded)
        except Exception:
            return {}

    async def create_outbound_call(self, to_number: str, session_id: str) -> dict:
        payload = {
            "connection_id": self.settings.telnyx_connection_id,
            "to": to_number,
            "from": self.settings.telnyx_outbound_from_number,
            "webhook_url": self.build_webhook_url(),
            "answering_machine_detection": self.settings.telnyx_answering_machine_detection,
            "client_state": self.encode_client_state({"session_id": session_id}),
        }
        return await self._post("/calls", payload)

    async def gather_using_ai(
        self,
        call_control_id: str,
        greeting: str,
        parameters: dict,
        gather_ended_speech: str,
    ) -> dict:
        payload = {
            "greeting": greeting,
            "parameters": parameters,
            "voice": self.settings.telnyx_ai_voice,
            "send_message_history_updates": False,
            "send_partial_results": False,
            "interruption_settings": {"user_response_timeout_ms": 15000},
            "gather_ended_speech": gather_ended_speech,
            "transcription": {"language": "en"},
        }
        return await self._post(f"/calls/{call_control_id}/actions/gather_using_ai", payload)

    async def speak(self, call_control_id: str, payload_text: str) -> dict:
        payload = {
            "payload": payload_text,
            "voice": self.settings.telnyx_ai_voice,
            "language": "en-US",
        }
        return await self._post(f"/calls/{call_control_id}/actions/speak", payload)

    async def hangup(self, call_control_id: str) -> dict:
        return await self._post(f"/calls/{call_control_id}/actions/hangup", {})

    async def _post(self, path: str, payload: dict) -> dict:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(f"{self.base_url}{path}", headers=self._headers(), json=payload)
            if response.is_error:
                detail = response.text
                raise httpx.HTTPStatusError(
                    f"{response.status_code} {response.reason_phrase}: {detail}",
                    request=response.request,
                    response=response,
                )
            return response.json()
