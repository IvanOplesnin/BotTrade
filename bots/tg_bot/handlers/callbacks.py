from aiogram import types
from aiogram.exceptions import TelegramBadRequest


async def clear_inline_keyboard(call: types.CallbackQuery) -> None:
    """Remove inline buttons from a callback message if Telegram still allows editing it."""
    if call.message is None:
        return

    try:
        await call.message.edit_reply_markup(reply_markup=None)
    except TelegramBadRequest as exc:
        message = str(exc)
        if (
                "message is not modified" in message
                or "message to edit not found" in message
                or "message can't be edited" in message
        ):
            return
        raise
