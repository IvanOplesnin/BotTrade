from __future__ import annotations

from typing import Any

from aiogram import Bot
from aiogram.types import Message

from bots.tg_bot.messages.formatting import TELEGRAM_SAFE_MESSAGE_LIMIT, split_message


async def answer_text(
        message: Message,
        text: str,
        *,
        limit: int = TELEGRAM_SAFE_MESSAGE_LIMIT,
        **kwargs: Any,
) -> None:
    chunks = split_message(text, limit=limit)
    reply_markup = kwargs.pop("reply_markup", None)

    for index, chunk in enumerate(chunks):
        params = dict(kwargs)
        if reply_markup is not None and index == len(chunks) - 1:
            params["reply_markup"] = reply_markup
        await message.answer(text=chunk, **params)


async def send_text(
        bot: Bot,
        chat_id: int,
        text: str,
        *,
        limit: int = TELEGRAM_SAFE_MESSAGE_LIMIT,
        **kwargs: Any,
) -> None:
    chunks = split_message(text, limit=limit)
    reply_markup = kwargs.pop("reply_markup", None)

    for index, chunk in enumerate(chunks):
        params = dict(kwargs)
        if reply_markup is not None and index == len(chunks) - 1:
            params["reply_markup"] = reply_markup
        await bot.send_message(chat_id=chat_id, text=chunk, **params)
