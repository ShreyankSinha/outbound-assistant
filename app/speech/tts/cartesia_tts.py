from __future__ import annotations

from collections.abc import AsyncIterator

from app.speech.tts.base_tts import BaseTTS


class CartesiaTTS(BaseTTS):
    async def synthesize_stream(self, text: str) -> AsyncIterator[bytes]:
        yield text.encode("utf-8")

    async def cancel(self) -> None:
        return None
