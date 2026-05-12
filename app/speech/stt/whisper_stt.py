from __future__ import annotations

from collections.abc import AsyncIterator

from app.speech.stt.base_stt import BaseSTT


class WhisperSTT(BaseSTT):
    async def transcribe_stream(self, audio_chunks: AsyncIterator[bytes]) -> AsyncIterator[str]:
        async for _ in audio_chunks:
            yield ""
