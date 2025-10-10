from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from tinkoff.invest import Account


def kb_list_accounts(accounts: list[Account| dict[str, str] ]):
    list_inline_buttons = [
        [InlineKeyboardButton(text=acc.name, callback_data=acc.id)]
        for acc in accounts
    ]
    return InlineKeyboardMarkup(inline_keyboard=list_inline_buttons)
