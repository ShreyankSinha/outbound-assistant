from __future__ import annotations

from app.schemas.session_state import SessionState


class SessionRegistry:
    def __init__(self) -> None:
        self._by_session_id: dict[str, SessionState] = {}
        self._by_call_control_id: dict[str, str] = {}
        self._by_call_session_id: dict[str, str] = {}

    def save(self, session: SessionState) -> SessionState:
        self._by_session_id[session.session_id] = session
        if session.call_control_id:
            self._by_call_control_id[session.call_control_id] = session.session_id
        if session.call_session_id:
            self._by_call_session_id[session.call_session_id] = session.session_id
        return session

    def get(self, session_id: str) -> SessionState | None:
        return self._by_session_id.get(session_id)

    def get_by_call_control_id(self, call_control_id: str | None) -> SessionState | None:
        if not call_control_id:
            return None
        session_id = self._by_call_control_id.get(call_control_id)
        return self._by_session_id.get(session_id) if session_id else None

    def get_by_call_session_id(self, call_session_id: str | None) -> SessionState | None:
        if not call_session_id:
            return None
        session_id = self._by_call_session_id.get(call_session_id)
        return self._by_session_id.get(session_id) if session_id else None

    def bind_telnyx_call(self, session: SessionState, call_control_id: str | None, call_session_id: str | None) -> SessionState:
        if call_control_id:
            session.call_control_id = call_control_id
            self._by_call_control_id[call_control_id] = session.session_id
        if call_session_id:
            session.call_session_id = call_session_id
            self._by_call_session_id[call_session_id] = session.session_id
        self._by_session_id[session.session_id] = session
        return session
