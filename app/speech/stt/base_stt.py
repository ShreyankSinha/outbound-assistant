from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator


class BaseSTT(ABC):
    @abstractmethod
    async def transcribe_stream(self, audio_chunks: AsyncIterator[bytes]) -> AsyncIterator[str]:
        raise NotImplementedError
