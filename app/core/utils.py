from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def new_session_id() -> str:
    return str(uuid4())
