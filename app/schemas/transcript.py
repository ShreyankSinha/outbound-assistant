from __future__ import annotations

from pydantic import BaseModel


class TranscriptEntry(BaseModel):
    role: str
    content: str
    timestamp: str
