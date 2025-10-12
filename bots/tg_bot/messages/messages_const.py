from typing import Any, Literal, Optional

from tinkoff.invest import PortfolioResponse

from database.pgsql.models import Instrument

START_TEXT = (
    "<b>Привет!</b> Я <b>TradingTMasterBot</b> 🐍📈\n\n"
    "Помогаю работать с Тинькофф Инвестициями: добавляю аккаунт, "
    "получаю портфель, считаю индикаторы (Donchian, ATR) и присылаю обновления цен.\n\n"
    "Открой меню команд или напиши <code>/help</code>, чтобы посмотреть возможности."
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


def text_add_account_message(indicators: list[dict[str, Any]]) -> str:
    return (f"Аккаунт успешно добавлен. Начинаем следить за инструментами:\n"
            f"{'\n'.join(f"{i['ticker']} - {i['direction']}" for i in indicators)}")


def text_delete_account_message(portfolio: PortfolioResponse) -> str:
    return (f"Аккаунт успешно удален. Удалены подписки на последние цены:\n"
            f"{'\n'.join(f"<b>{p.ticker}</b>" for p in portfolio.positions)}")


def text_add_favorites_instruments(instruments: list[Instrument]) -> str:
    return (f"Начинаем следить за инструментами:\n"
            f"{'\n'.join(f"✅ <b>{i.ticker}</b>" for i in instruments)}")


def text_uncheck_favorites_instruments(instruments: list[Instrument]) -> str:
    return (f"Перестаем следить за инструментами:\n"
            f"{'\n'.join(f"✅ <b>{i.ticker}</b>" for i in instruments)}")


def _fmt(x: Optional[float], nd: int = 2) -> str:
    return ("{0:,.%df}" % nd).format(x).replace(",", " ") if x is not None else "—"


def text_favorites_breakout(
        ind: Instrument,
        side: Literal["long", "short"],
        *,
        last_price: Optional[float] = None,
        price_point_value: Optional[float] = None,  # «стоимость пункта цены», если есть
) -> str:
    """
    Уведомление для избранного при пробое 55-дневного канала.
    side='long'  → пробой верхней границы (donchian_long_55)
    side='short' → пробой нижней границы (donchian_short_55)
    """
    boundary = ind.donchian_long_55 if side == "long" else ind.donchian_short_55
    atr = ind.atr14 or 0.0

    # уровни: граница - atr/2, граница + atr/2, граница + atr, граница + 1.5*atr
    lvl_m_half = boundary - atr / 2 if 'long' else boundary + atr / 2
    lvl_p_half = boundary + atr / 2 if 'long' else boundary - atr / 2
    lvl_p_1x = boundary + atr if 'long' else boundary - atr / 2
    lvl_p_1_5x = boundary + 1.5 * atr if 'long' else boundary - atr / 2

    side_txt = "Пробой ↑ верхней границы (55)" if side == "long" else "Пробой ↓ нижней границы (55)"

    lines = [
        f"<b>{side_txt}</b>",
        f"{ind.ticker} • {ind.instrument_id}",
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

def text_stop_long_position(ind: Instrument, *, last_price: Optional[float] = None) -> str:
    """
    Для открытого ЛОНГА: пробой вниз нижней границы Donchian(20).
    """
    lines = [
        "<b>Стоп по лонгу (пробой нижней границы 20)</b>",
        f"{ind.ticker} • {ind.instrument_id}",
    ]
    if last_price is not None:
        lines.append(f"Цена последней сделки: <b>{_fmt(last_price, 4)}</b>")
    lines.append(f"Граница (SHORT_20): <b>{_fmt(ind.donchian_short_20, 4)}</b>")
    return "\n".join(lines)


def text_stop_short_position(ind: Instrument, *, last_price: Optional[float] = None) -> str:
    """
    Для открытого ШОРТА: пробой вверх верхней границы Donchian(20).
    """
    lines = [
        "<b>Стоп по шорту (пробой верхней границы 20)</b>",
        f"{ind.ticker} • {ind.instrument_id}",
    ]
    if last_price is not None:
        lines.append(f"Цена последней сделки: <b>{_fmt(last_price, 4)}</b>")
    lines.append(f"Граница (LONG_20): <b>{_fmt(ind.donchian_long_20, 4)}</b>")
    return "\n".join(lines)
