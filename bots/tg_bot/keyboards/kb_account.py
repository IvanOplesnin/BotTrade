from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from tinkoff.invest import Account, FavoriteInstrument
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
        if f'set:{i.uid}' in set_favorite:
            return True
        else:
            return False

    list_inline_buttons = [
        [InlineKeyboardButton(text='Добавить все', callback_data='add_all')]
    ]
    for instrument in instruments:
        if is_choice(instrument):
            text = f"✅-{instrument.name}"
        else:
            text = f"☐-{instrument.name}"

        list_inline_buttons.append([InlineKeyboardButton(
            text=text, callback_data=f"set:{instrument.uid}"
        )])

    success_cancel_button = [
        InlineKeyboardButton(text='Добавить', callback_data='add'),
        InlineKeyboardButton(text='Отменить', callback_data='cancel')
    ]
    list_inline_buttons.append(success_cancel_button)

    return InlineKeyboardMarkup(inline_keyboard=list_inline_buttons)

def kb_list_uncheck(instruments: list[Instrument], selected: set[str]) -> InlineKeyboardMarkup:
    """
    instruments: Iterable[Instrument-like] c полями .instrument_id и .ticker
    selected: множество строк 'unset:<uid>'
    """
    rows = []
    for instr in instruments:
        uid = instr.instrument_id
        label = instr.ticker
        key = f"unset:{uid}"
        checked = "✅" if key in selected else "☐"
        rows.append([InlineKeyboardButton(text=f"{checked} {label}", callback_data=key)])
    rows.append([
        InlineKeyboardButton(text="🗑 Удалить выбранные", callback_data="remove"),
        InlineKeyboardButton(text="🧹 Удалить все", callback_data="remove_all"),
    ])
    rows.append([InlineKeyboardButton(text="✖ Отмена", callback_data="cancel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)
