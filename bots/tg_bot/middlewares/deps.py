from typing import Callable, Dict, Any, Awaitable
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

class DepsMiddleware(BaseMiddleware):
    def __init__(self, **deps):
        self._deps = deps

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        data.update(self._deps)  
        return await handler(event, data)