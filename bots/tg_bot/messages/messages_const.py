import asyncio
from typing import Any, Literal, Optional, Sequence, Set, List

from tinkoff.invest import PortfolioResponse

from clients.tinkoff.name_service import NameService
from database.pgsql.enums import Direction
from database.pgsql.models import Instrument, AccountInstrument

START_TEXT = (
    "<b>Привет!</b> Я <b>TradingTMasterBot</b> 🐍📈\n\n"
    "Помогаю работать с Т-Инвестициями: добавляю аккаунт, "
    "получаю портфель, считаю индикаторы (Donchian, ATR) и присылаю обновления цен.\n\n"
    "Открой меню команд или напиши /help, чтобы посмотреть возможности."
)

HELP_TEXT = (
    "<b>Справка</b>\n\n"
    "<b>Основные команды:</b>\n"
    "• /start — приветствие и краткая информация о боте.\n"
    "• /help — эта справка.\n\n"
    "<b>Аккаунты:</b>\n"
    "• /add_account_check — выбрать и добавить аккаунт для отслеживания.\n"
    "• /remove_account_check — удалить ранее добавленный аккаунт.\n\n"
    "<b>Инструменты:</b>\n"
    "• /add_instruments_for_check — добавить избранные инструменты для отслеживания.\n"
    "• /uncheck_instruments — перестать отслеживать выбранные инструменты.\n\n"
    "<b>Информация:</b>\n"
    "• /info — Показывает информацию об отслеживаемых инструментах.\n"
    "• /check_notify — Просмотреть информацию об оповещениях.\n\n"
    "<b>Что делает бот при добавлении аккаунта</b>:\n"
    "1) Загружает портфель и сохраняет инструменты в базу.\n"
    "2) Рассчитывает индикаторы: Donchian 55/20 и ATR(14).\n"
    "3) Подписывается на ленту цен (last_price) по инструментам из портфеля.\n\n"
    "<b>Подсказки:</b>\n"
    "• Если нужно остановить обработку текущей команды — нажми кнопку Отменить или начни заново.\n"
    "• Кнопки и подсказки появляются по ходу сценария — следуй инструкциям бота.\n\n"
    "<b>Технически</b>:\n"
    "— Бэк использует aiogram v3 и асинхронный клиент Тинькофф.\n"
    "— Данные хранятся в БД; вычисления индикаторов делаются по завершённым свечам.\n"
)


async def text_add_account_message(
        indicators: list[AccountInstrument],
        name_service: NameService
) -> str:
    uids = [i.instrument_id for i in indicators]
    names = await asyncio.gather(*(name_service.get_name(uid) for uid in uids))

    lines = []
    for i, name in zip(indicators, names):
        direction = i.direction
        direction_str = str(direction).upper() if direction is not None else "—"
        lines.append(f"✅ <b>{name}</b> — {direction_str}")

    body = "\n".join(lines) if lines else "нет инструментов."
    return "Аккаунт успешно добавлен. Начинаем следить за инструментами:\n" + body


async def text_delete_account_message(
        portfolio: PortfolioResponse,
        name_service: NameService,
) -> str:
    positions = getattr(portfolio, "positions", []) or []
    uids = [p.instrument_uid for p in positions]
    names = await asyncio.gather(*(name_service.get_name(uid) for uid in uids))

    lines = [f"❌ <b>{name}</b>" for name in names]
    body = "\n".join(lines) if lines else "подписок не было."
    return "Аккаунт успешно удалён. Удалены подписки на последние цены:\n" + body


async def text_add_favorites_instruments(instruments: list[Instrument],
                                         name_service: NameService) -> str:
    names = await asyncio.gather(
        *(name_service.get_name(i.instrument_id) for i in instruments)
    )
    lines = [
        f"✅ <b>{name}</b> — {i.ticker}"
        for name, i in zip(names, instruments)
    ]
    return "Добавлены инструменты:\n" + ("\n".join(lines) if lines else "ничего не выбрано.")


async def text_uncheck_favorites_instruments(
        instruments: list[Instrument],
        name_service: NameService,
) -> str:
    uids = [i.instrument_id for i in instruments]
    names = await asyncio.gather(*(name_service.get_name(uid) for uid in uids))

    lines = [f"⚪ <b>{name}</b>" for name in names]
    body = "\n".join(lines) if lines else "ничего не выбрано."
    return "Перестаём следить за инструментами:\n" + body


def _fmt(x: Optional[float], nd: int = 2) -> str:
    return ("{0:,.%df}" % nd).format(x).replace(",", " ") if x is not None else "—"


async def text_favorites_breakout(
        ind: Instrument,
        side: Literal["long", "short"],
        name_service: NameService,
        *,
        last_price: Optional[float] = None,
        price_point_value: Optional[float] = None,
        # «стоимость пункта цены», если есть
) -> str:
    """
    Уведомление для избранного при пробое 55-дневного канала.
    side='long'  → пробой верхней границы (donchian_long_55)
    side='short' → пробой нижней границы (donchian_short_55)
    """
    boundary = ind.donchian_long_55 if side == "long" else ind.donchian_short_55
    atr = ind.atr14 or 0.0

    # уровни: граница - atr/2, граница + atr/2, граница + atr, граница + 1.5*atr
    lvl_m_half = boundary - atr / 2 if side == "long" else boundary + atr / 2
    lvl_p_half = boundary + atr / 2 if side == "long" else boundary - atr / 2
    lvl_p_1x = boundary + atr if side == "long" else boundary - atr
    lvl_p_1_5x = boundary + 1.5 * atr if side == "long" else boundary - atr * 1.5

    side_txt = "Пробой ↑ верхней границы (55)" if side == "long" else "Пробой ↓ нижней границы (55)"

    lines = [
        f"<b>{side_txt}</b>",
        f"{ind.ticker} • {await name_service.get_name(ind.instrument_id)}",
    ]
    if last_price is not None:
        lines.append(f"Цена последней сделки: <b>{_fmt(last_price, 4)}</b>")
    lines += [
        f"Граница: <b>{_fmt(boundary, 4)}</b>",
        f"ATR(14): <b>{_fmt(ind.atr14, 4)}</b>",
    ]
    if price_point_value is not None:
        lines.append(f"Стоимость пункта: <b>{_fmt(price_point_value, 4)}</b>")

    if side == "long":
        lines += [
            "Уровни:",
            f"• Граница − ATR/2: <b>{_fmt(lvl_m_half, 4)}</b>",
            f"• Граница + ATR/2: <b>{_fmt(lvl_p_half, 4)}</b>",
            f"• Граница + ATR:   <b>{_fmt(lvl_p_1x, 4)}</b>",
            f"• Граница + 1.5 ATR: <b>{_fmt(lvl_p_1_5x, 4)}</b>",
        ]
    elif side == "short":
        lines += [
            "Уровни:",
            f"• Граница + ATR/2: <b>{_fmt(lvl_m_half, 4)}</b>",
            f"• Граница - ATR/2: <b>{_fmt(lvl_p_half, 4)}</b>",
            f"• Граница - ATR:   <b>{_fmt(lvl_p_1x, 4)}</b>",
            f"• Граница - 1.5 ATR: <b>{_fmt(lvl_p_1_5x, 4)}</b>",
        ]
    return "\n".join(lines)


# ========== СЧЕТА: пробой 20-дневного канала (стоп по позиции) ==========

async def text_stop_long_position(ind: Instrument, *, last_price: Optional[float] = None,
                                  name_service: NameService) -> str:
    """
    Для открытого ЛОНГА: пробой вниз нижней границы Donchian(20).
    """
    lines = [
        "<b>Стоп по лонгу (пробой нижней границы 20)</b>",
        f"{ind.ticker} • {await name_service.get_name(ind.instrument_id)}",
    ]
    if last_price is not None:
        lines.append(f"Цена последней сделки: <b>{_fmt(last_price, 4)}</b>")
    lines.append(f"Граница (SHORT_20): <b>{_fmt(ind.donchian_short_20, 4)}</b>")
    return "\n".join(lines)


async def text_stop_short_position(ind: Instrument, *,
                                   last_price: Optional[float] = None,
                                   name_service: NameService) -> str:
    """
    Для открытого ШОРТА: пробой вверх верхней границы Donchian(20).
    """
    lines = [
        "<b>Стоп по шорту (пробой верхней границы 20)</b>",
        f"{ind.ticker} • {await name_service.get_name(ind.instrument_id)}",
    ]
    if last_price is not None:
        lines.append(f"Цена последней сделки: <b>{_fmt(last_price, 4)}</b>")
    lines.append(f"Граница (LONG_20): <b>{_fmt(ind.donchian_long_20, 4)}</b>")
    return "\n".join(lines)


async def info_notify_message(instr: Sequence[Instrument], name_service: NameService):
    async def message_text(ins: Instrument, num):
        name = await name_service.get_name(ins.instrument_id)
        return f"{num:<2}: <b>{i.ticker:<5}</b> | <b>{name}</b>\n"

    with_notify = []
    without_notify = []
    only_check = []
    for i in instr:
        if i.check:
            only_check.append(i)
            if i.to_notify:
                with_notify.append(i)
            if not i.to_notify:
                without_notify.append(i)

    msg = (f"<b>Информация по оповещениям</b>\n"
           f"Следим за <b>{len(only_check)}</b> инструментами\n\n")

    if with_notify:
        msg += "Инструменты по которым ждем оповещение:\n"
        for index, i in enumerate(with_notify):
            msg += await message_text(i, index)
        msg += "\n"

    if without_notify:
        msg += "Инструменты по которым сегодня было оповещение:\n"
        for index, i in enumerate(without_notify):
            msg += await message_text(i, index)

    return msg


async def msg_portfolio_notify(add: List[dict[str, Any]], del_: Set[str], ns: NameService):
    text = "<b>Изменение информации по позициям:</b>\n"
    if add:
        text += "Вошли в позицию по:\n"
        for i in add:
            name = await ns.get_name(i["instrument_id"])
            text += f"<b>{name}</b> | {i['direction']}\n"
    if del_:
        text += "Вышли из позиций по:\n"
        for uid in del_:
            name = await ns.get_name(uid)
            text += f"<b>{name}</b>\n"
    return text


async def info_database_message(
        row: Sequence[tuple[Instrument, Optional[AccountInstrument]]],
        name_service: NameService,
) -> str:
    if not row:
        return "Вы не следите за инструментами"

    def bold(x: str | float | int) -> str:
        if x:
            return f"<b>{x}</b>"
        else:
            return ""

    def get_exit_channel(inst: Instrument, direction):
        if direction == Direction.LONG.value:
            return inst.donchian_short_20
        elif direction == Direction.SHORT.value:
            return inst.donchian_long_20
        return None

    msg_out_position = f"{bold("Инструменты не в позиции:")}\n"
    msg_in_position = f"{bold("Инструменты в позиции:")}\n"
    for i, ai in row:
        name = bold(await name_service.get_name(i.instrument_id))
        ticker = bold(i.ticker)
        if not ai and i.check:
            msg_out_position += f"• {name} | {ticker}\n"
            msg_out_position += (
                f"   КД55: |{bold(i.donchian_short_55)} - {bold(i.donchian_long_55)}|\n\n"
            )
        elif ai:
            msg_in_position += f"• {name} | {ticker} - {bold(ai.direction)}\n"
            msg_in_position += f"   ЦЗ: {bold(get_exit_channel(i, ai.direction))}\n\n"

    msg = f"{msg_out_position}\n{msg_in_position}"
    return msg
