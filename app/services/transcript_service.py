from __future__ import annotations

from app.core.utils import utc_now_iso
from app.schemas.session_state import SessionState
from app.schemas.transcript import TranscriptEntry


class TranscriptService:
    def add_entry(self, session: SessionState, role: str, content: str) -> SessionState:
        session.transcript.append(TranscriptEntry(role=role, content=content, timestamp=utc_now_iso()))
        return session
