from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator

from app.schemas.session_state import SessionState


class BaseTransport(ABC):
    @abstractmethod
    async def start_session(self, session: SessionState) -> SessionState:
        raise NotImplementedError

    @abstractmethod
    async def end_session(self, session: SessionState, reason: str) -> SessionState:
        raise NotImplementedError

    @abstractmethod
    async def receive_customer_input(self, session: SessionState) -> str:
        raise NotImplementedError

    @abstractmethod
    async def send_agent_response(self, session: SessionState, response_text: str) -> None:
        raise NotImplementedError

    @abstractmethod
    async def handle_interrupt(self, session: SessionState) -> None:
        raise NotImplementedError

    @abstractmethod
    async def stream_audio(self, session: SessionState, audio_stream: AsyncIterator[bytes]) -> None:
        raise NotImplementedError
