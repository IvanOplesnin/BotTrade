from __future__ import annotations

from typing import Any, Awaitable, Callable, Protocol

Handler = Callable[[Any], Awaitable[None]]


class MessageBus(Protocol):
    def subscribe(self, topic: str, handler: Handler) -> None:
        ...

    async def publish(self, topic: str, data: Any) -> None:
        ...

    async def start(self) -> None:
        ...

    async def stop(self) -> None:
        ...
