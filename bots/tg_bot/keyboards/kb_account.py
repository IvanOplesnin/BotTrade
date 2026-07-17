from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from clients.tinkoff.name_service import NameService
from clients.tinkoff.sdk import (
    Account,
    FavoriteInstrument,
    sdk_instrument_name,
    sdk_instrument_ticker,
    sdk_instrument_uid,
)
from database.pgsql.models import Account as AccountDb, Instrument


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


def kb_list_favorites(instruments: list[FavoriteInstrument], set_favorite: set[str]):
    def is_choice(i: FavoriteInstrument):
        uid = sdk_instrument_uid(i)
        if f'set:{uid}' in set_favorite:
            return True
        else:
            return False

    list_inline_buttons = [
        [InlineKeyboardButton(text='Добавить все', callback_data='add_all')]
    ]
    for instrument in instruments:
        uid = sdk_instrument_uid(instrument)
        ticker = sdk_instrument_ticker(instrument, default=uid)
        name = sdk_instrument_name(instrument, default=ticker)
        if is_choice(instrument):
            text = f"✅-{ticker} | {name}"
        else:
            text = f"☐-{ticker} | {name}"

        list_inline_buttons.append([InlineKeyboardButton(
            text=text, callback_data=f"set:{uid}"
        )])

    success_cancel_button = [
        InlineKeyboardButton(text='Добавить', callback_data='add'),
        InlineKeyboardButton(text='Отменить', callback_data='cancel')
    ]
    list_inline_buttons.append(success_cancel_button)

    return InlineKeyboardMarkup(inline_keyboard=list_inline_buttons)


async def kb_list_uncheck(instruments: list[Instrument], selected: set[str],
                          name_service: NameService) -> InlineKeyboardMarkup:
    """
    instruments: Iterable[Instrument-like] c полями .instrument_id и .ticker
    selected: множество строк 'unset:<uid>'
    """
    rows = []
    for instr in instruments:
        uid = instr.instrument_id
        name = await name_service.get_name(uid)
        ticker = instr.ticker
        key = f"unset:{uid}"
        checked = "✅" if key in selected else "☐"
        rows.append([InlineKeyboardButton(text=f"{checked} {ticker} | {name}", callback_data=key)])
    rows.append([
        InlineKeyboardButton(text="🗑 Удалить выбранные", callback_data="remove"),
        InlineKeyboardButton(text="🧹 Удалить все", callback_data="remove_all"),
    ])
    rows.append([InlineKeyboardButton(text="✖ Отмена", callback_data="cancel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def kb_instr_info(instruments: list[Instrument], name_service: NameService) -> InlineKeyboardMarkup:
    rows = []
    for instr in instruments:
        uid = instr.instrument_id
        name = await name_service.get_name(uid)
        ticker = instr.ticker
        print(f"info:{uid}")
        rows.append([InlineKeyboardButton(text=f"{ticker} | {name}", callback_data=f"info:{uid}")])

    rows.append([InlineKeyboardButton(text="✖ Отмена", callback_data="cancel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def kb_short_long():
    rows = [
        [InlineKeyboardButton(text='SHORT', callback_data='short'),
         InlineKeyboardButton(text='LONG', callback_data='long')],
        [InlineKeyboardButton(text='Отменить', callback_data='cancel')]
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)
