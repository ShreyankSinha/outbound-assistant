from __future__ import annotations

from collections.abc import AsyncIterator

from app.transport.telnyx_transport import TelnyxTransport


class GradioTransport(TelnyxTransport):
    """Debug transport that shares the same contract as the telephony path."""

    async def stream_audio(self, session, audio_stream: AsyncIterator[bytes]) -> None:
        async for _ in audio_stream:
            break
