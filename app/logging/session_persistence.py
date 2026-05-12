from __future__ import annotations

from pathlib import Path

import orjson

from app.config import get_settings
from app.schemas.session_state import SessionState


class SessionPersistence:
    def __init__(self, log_dir: str | None = None) -> None:
        settings = get_settings()
        self.log_dir = Path(log_dir or settings.log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)

    def persist(self, session: SessionState) -> Path:
        path = self.log_dir / f"{session.session_id}.json"
        path.write_bytes(orjson.dumps(session.model_dump(), option=orjson.OPT_INDENT_2))
        return path
