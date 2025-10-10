from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from tinkoff.invest import Account
from database.pgsql.models import Account as AccountDb


def kb_list_accounts(accounts: list[Account]):
    list_inline_buttons = [
        [InlineKeyboardButton(text=acc.name, callback_data=acc.id)]
        for acc in accounts
    ]
    list_inline_buttons.append([InlineKeyboardButton(text='Отменить', callback_data='cancel')])
    return InlineKeyboardMarkup(inline_keyboard=list_inline_buttons)


def kb_list_accounts_delete(accounts: list[AccountDb]):
    list_inline_buttons = [
        [InlineKeyboardButton(text=acc.name, callback_data=acc.account_id)]
        for acc in accounts
    ]
    list_inline_buttons.append([InlineKeyboardButton(text='Отменить', callback_data='cancel')])
    return InlineKeyboardMarkup(inline_keyboard=list_inline_buttons)
