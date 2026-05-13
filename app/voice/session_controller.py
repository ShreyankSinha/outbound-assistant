from __future__ import annotations

from app.core.enums import CallState
from app.orchestration.call_lifecycle_manager import CallLifecycleManager
from app.schemas.session_state import SessionState
from app.transport.base_transport import BaseTransport


class VoiceSessionController:
    def __init__(self, transport: BaseTransport) -> None:
        self.transport = transport
        self.lifecycle = CallLifecycleManager()

    async def start_outbound_call(self, session: SessionState) -> SessionState:
        session = await self.transport.start_session(session)
        if not self.transport.manages_live_call_lifecycle:
            self.lifecycle.transition(session, CallState.ANSWERED)
            self.lifecycle.transition(session, CallState.ACTIVE)
        return session

    async def play_response(self, session: SessionState, response_text: str) -> None:
        await self.transport.send_agent_response(session, response_text)

    async def interrupt(self, session: SessionState) -> None:
        await self.transport.handle_interrupt(session)

    async def end_call(self, session: SessionState, reason: str) -> SessionState:
        return await self.transport.end_session(session, reason)
