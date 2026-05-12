from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator


class BaseTTS(ABC):
    @abstractmethod
    async def synthesize_stream(self, text: str) -> AsyncIterator[bytes]:
        raise NotImplementedError

    @abstractmethod
    async def cancel(self) -> None:
        raise NotImplementedError
