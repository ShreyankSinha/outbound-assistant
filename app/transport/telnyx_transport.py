from __future__ import annotations

from collections.abc import AsyncIterator

from app.core.enums import CallState
from app.core.exceptions import ProviderError
from app.orchestration.call_lifecycle_manager import CallLifecycleManager
from app.schemas.session_state import SessionState
from app.transport.base_transport import BaseTransport
from app.transport.telnyx_api import TelnyxCallControlClient


class TelnyxTransport(BaseTransport):
    manages_live_call_lifecycle = True

    def __init__(self) -> None:
        self.lifecycle = CallLifecycleManager()
        self.client = TelnyxCallControlClient()

    async def start_session(self, session: SessionState) -> SessionState:
        session.telephony_provider = "telnyx"
        self.lifecycle.transition(session, CallState.RINGING)
        if not session.call_target.startswith("+"):
            raise ProviderError("Telnyx outbound calls require an E.164 destination number.")
        try:
            response = await self.client.create_outbound_call(session.call_target, session.session_id)
        except Exception as exc:
            session.errors.append(f"telnyx_create_call_failed:{exc}")
            self.lifecycle.transition(session, CallState.FAILED)
            raise ProviderError(f"Failed to create Telnyx outbound call: {exc}") from exc
        data = response.get("data", {})
        session.call_control_id = data.get("call_control_id") or session.call_control_id
        session.call_leg_id = data.get("call_leg_id") or session.call_leg_id
        session.call_session_id = data.get("call_session_id") or session.call_session_id
        return session

    async def end_session(self, session: SessionState, reason: str) -> SessionState:
        session.resolution_notes.append(f"call_end_reason:{reason}")
        if session.call_control_id and session.call_state not in {CallState.ENDED, CallState.FAILED}:
            try:
                await self.client.hangup(session.call_control_id)
            except Exception as exc:
                session.errors.append(f"telnyx_hangup_failed:{exc}")
        if session.call_state != CallState.ENDED:
            self.lifecycle.transition(session, CallState.ENDED)
        return session

    async def receive_customer_input(self, session: SessionState) -> str:
        return session.customer_last_message

    async def send_agent_response(self, session: SessionState, response_text: str) -> None:
        session.agent_last_message = response_text

    async def handle_interrupt(self, session: SessionState) -> None:
        session.resolution_notes.append("customer_interrupted")

    async def stream_audio(self, session: SessionState, audio_stream: AsyncIterator[bytes]) -> None:
        async for _ in audio_stream:
            break

    async def start_ai_gather(self, session: SessionState, opening_text: str) -> SessionState:
        if not session.call_control_id:
            raise ProviderError("Cannot start AI gather without a Telnyx call_control_id.")
        try:
            response = await self.client.gather_using_ai(
                call_control_id=session.call_control_id,
                greeting=opening_text,
                parameters=self._build_gather_parameters(),
                gather_ended_speech="Thank you. We have what we need and will update the account accordingly. Goodbye.",
            )
        except Exception as exc:
            session.errors.append(f"telnyx_ai_gather_failed:{exc}")
            raise ProviderError(f"Failed to start Telnyx AI gather: {exc}") from exc
        data = response.get("data", {})
        session.telnyx_conversation_id = data.get("conversation_id")
        session.telnyx_gather_started = True
        return session

    async def leave_voicemail(self, session: SessionState, voicemail_text: str) -> SessionState:
        if not session.call_control_id:
            raise ProviderError("Cannot leave voicemail without a Telnyx call_control_id.")
        try:
            await self.client.speak(session.call_control_id, voicemail_text)
        except Exception as exc:
            session.errors.append(f"telnyx_voicemail_failed:{exc}")
            raise ProviderError(f"Failed to leave voicemail over Telnyx: {exc}") from exc
        session.telnyx_voicemail_played = True
        return session

    def decode_client_state(self, client_state: str | None) -> dict[str, str]:
        return self.client.decode_client_state(client_state)

    @staticmethod
    def _build_gather_parameters() -> dict:
        return {
            "type": "object",
            "properties": {
                "resolution_status": {
                    "type": "string",
                    "enum": [
                        "payment_committed",
                        "callback_requested",
                        "human_requested",
                        "disputed",
                        "unresolved",
                    ],
                    "description": "Classify the customer's final position on the call.",
                },
                "payment_date": {
                    "type": "string",
                    "description": "If the customer committed to payment, capture the promised payment date or time.",
                },
                "callback_time": {
                    "type": "string",
                    "description": "If the customer asked for a callback, capture when they want to be called back.",
                },
                "notes": {
                    "type": "string",
                    "description": "A concise summary of what the customer said and any action agreed.",
                },
            },
            "required": ["resolution_status", "notes"],
        }
