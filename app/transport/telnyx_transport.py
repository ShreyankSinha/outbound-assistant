from __future__ import annotations

from collections.abc import AsyncIterator

from app.core.enums import CallState
from app.orchestration.call_lifecycle_manager import CallLifecycleManager
from app.schemas.session_state import SessionState
from app.transport.base_transport import BaseTransport


class TelnyxTransport(BaseTransport):
    """Mocked Telnyx-ready transport for the first PoC pass."""

    def __init__(self) -> None:
        self.lifecycle = CallLifecycleManager()

    async def start_session(self, session: SessionState) -> SessionState:
        self.lifecycle.transition(session, CallState.RINGING)
        return session

    async def end_session(self, session: SessionState, reason: str) -> SessionState:
        session.resolution_notes.append(f"call_end_reason:{reason}")
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
