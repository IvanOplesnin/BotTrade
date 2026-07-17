from __future__ import annotations

import asyncio
from typing import Any, Literal, Optional, Sequence

from bots.tg_bot.messages.formatting import calc_count_contracts, fmt_number
from clients.tinkoff.name_service import NameService
from clients.tinkoff.portfolio_svc import PortfolioOut
from database.pgsql.models import Instrument


async def text_add_favorites_instruments(
        instruments: Sequence[Any],
        name_service: NameService,
) -> str:
    names = await asyncio.gather(
        *(name_service.get_name(item.instrument_id) for item in instruments)
    )
    lines = [
        f"✅ <b>{name}</b> — {item.ticker}"
        for name, item in zip(names, instruments)
    ]
    return "Добавлены инструменты:\n" + ("\n".join(lines) if lines else "ничего не выбрано.")


async def text_uncheck_favorites_instruments(
        instruments: Sequence[Any],
        name_service: NameService,
) -> str:
    uids = [item.instrument_id for item in instruments]
    names = await asyncio.gather(*(name_service.get_name(uid) for uid in uids))

    lines = [f"⚪ <b>{name}</b>" for name in names]
    body = "\n".join(lines) if lines else "ничего не выбрано."
    return "Перестаём следить за инструментами:\n" + body


async def text_favorites_breakout(
        ind: Instrument,
        side: Literal["long", "short"],
        name_service: NameService,
        *,
        last_price: Optional[float] = None,
        price_point_value: Optional[float] = None,
        calculation_from_the_last_price: bool = False,
        portfolios: list[PortfolioOut] = None,
) -> str:
    boundary = ind.donchian_long_55 if side == "long" else ind.donchian_short_55
    bound = last_price if calculation_from_the_last_price else boundary
    atr = ind.atr14 or 0.0

    lvl_m_half = bound - atr / 2 if side == "long" else bound + atr / 2
    lvl_p_half = bound + atr / 2 if side == "long" else bound - atr / 2
    lvl_p_1x = bound + atr if side == "long" else bound - atr
    lvl_p_1_5x = bound + 1.5 * atr if side == "long" else bound - atr * 1.5

    lines = []
    if last_price is not None and not calculation_from_the_last_price:
        side_txt = "<b>ПРОРЫВ</b> ↑ (55)" if side == "long" else "<b>ПРОРЫВ</b> ↓ (55)"
        lines.append(f"<b>{side_txt}</b>")

    side_arrow = "↑" if side == "long" else "↓"

    if calculation_from_the_last_price:
        side_txt = f"<b>РАСЧЁТ УРОВНЕЙ</b> <b>{side_arrow}</b>"
        lines.append(f"<b>{side_txt}</b>")

    lines.append("")
    lines.append(f"<b>{ind.ticker} • {await name_service.get_name(ind.instrument_id)}</b>")

    if not calculation_from_the_last_price:
        lines.append(f"• Граница: <b>{fmt_number(boundary, 4)}</b>")
    else:
        lines.append(f"• Вход: <b>{fmt_number(last_price, 4)}</b>")

    if portfolios:
        for portfolio in portfolios:
            count = calc_count_contracts(portfolio, atr, price_point_value)
            lines.append(f"• РЮ({portfolio.name}): <b>{count}</b>")

    lines.append(f"• Стоп: <b>{fmt_number(lvl_m_half, 4)}</b>")
    lines.append("")
    lines.append("<b>Уровни</b>")
    lines += [
        f"• Юнит 2: <b>{fmt_number(lvl_p_half, 4)}</b>",
        f"• Юнит 3: <b>{fmt_number(lvl_p_1x, 4)}</b>",
        f"• Юнит 4: <b>{fmt_number(lvl_p_1_5x, 4)}</b>",
    ]
    lines.append("")
    lines.append("<b>Показатели</b>")
    if portfolios:
        for portfolio in portfolios:
            lines.append(f"• РП({portfolio.name}):{fmt_number(float(portfolio.total_amount), 2)}")
    lines += [
        f"• ATR(14): <b>{fmt_number(atr, 4)}</b>",
        f"• СПЦ: <b>{fmt_number(price_point_value, 4)}</b>",
    ]
    if not calculation_from_the_last_price:
        lines.append(f"• ЦПС: <b>{fmt_number(last_price, 4)}</b>")

    return "\n".join(lines)


async def text_stop_long_position(
        ind: Instrument,
        *,
        last_price: Optional[float] = None,
        name_service: NameService,
) -> str:
    lines = [
        "<b>Стоп по лонгу (пробой нижней границы 20)</b>",
        f"{ind.ticker} • {await name_service.get_name(ind.instrument_id)}",
    ]
    if last_price is not None:
        lines.append(f"Цена последней сделки: <b>{fmt_number(last_price, 4)}</b>")
    lines.append(f"Граница (SHORT_20): <b>{fmt_number(ind.donchian_short_20, 4)}</b>")
    return "\n".join(lines)


async def text_stop_short_position(
        ind: Instrument,
        *,
        last_price: Optional[float] = None,
        name_service: NameService,
) -> str:
    lines = [
        "<b>Стоп по шорту (пробой верхней границы 20)</b>",
        f"{ind.ticker} • {await name_service.get_name(ind.instrument_id)}",
    ]
    if last_price is not None:
        lines.append(f"Цена последней сделки: <b>{fmt_number(last_price, 4)}</b>")
    lines.append(f"Граница (LONG_20): <b>{fmt_number(ind.donchian_long_20, 4)}</b>")
    return "\n".join(lines)
