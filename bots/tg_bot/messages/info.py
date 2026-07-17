from __future__ import annotations

from typing import Any, Optional, Sequence, Set

from clients.tinkoff.name_service import NameService
from database.pgsql.enums import Direction
from database.pgsql.models import AccountInstrument, Instrument


async def info_notify_message(
        instruments: Sequence[Instrument],
        name_service: NameService,
) -> str:
    async def message_text(instrument: Instrument, num: int) -> str:
        name = await name_service.get_name(instrument.instrument_id)
        return f"{num:<2}: <b>{instrument.ticker:<5}</b> | <b>{name}</b>\n"

    with_notify = []
    without_notify = []
    checked = []
    for instrument in instruments:
        if instrument.check:
            checked.append(instrument)
            if instrument.to_notify:
                with_notify.append(instrument)
            else:
                without_notify.append(instrument)

    msg = (
        f"<b>Информация по оповещениям</b>\n"
        f"Следим за <b>{len(checked)}</b> инструментами\n\n"
    )

    if with_notify:
        msg += "Инструменты по которым ждем оповещение:\n"
        for index, instrument in enumerate(with_notify):
            msg += await message_text(instrument, index)
        msg += "\n"

    if without_notify:
        msg += "Инструменты по которым сегодня было оповещение:\n"
        for index, instrument in enumerate(without_notify):
            msg += await message_text(instrument, index)

    return msg


async def msg_portfolio_notify(add: list[dict[str, Any]], del_: Set[str], ns: NameService):
    text = "<b>Изменение информации по позициям:</b>\n"
    if add:
        text += "Вошли в позицию по:\n"
        for item in add:
            name = await ns.get_name(item["instrument_id"])
            text += f"<b>{name}</b> | {item['direction']}\n"
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

    def bold(value: str | float | int) -> str:
        return f"<b>{value}</b>" if value else ""

    def get_exit_channel(inst: Instrument, direction):
        if direction == Direction.LONG.value:
            return inst.donchian_short_20
        if direction == Direction.SHORT.value:
            return inst.donchian_long_20
        return None

    msg_out_position = f"{bold('Инструменты не в позиции:')}\n"
    msg_in_position = f"{bold('Инструменты в позиции:')}\n"
    for instrument, account_instrument in row:
        name = bold(await name_service.get_name(instrument.instrument_id))
        ticker = bold(instrument.ticker)
        if not account_instrument and instrument.check:
            msg_out_position += f"• {name} | {ticker}\n"
            msg_out_position += (
                f"   КД55: |{bold(instrument.donchian_short_55)} - "
                f"{bold(instrument.donchian_long_55)}|\n\n"
            )
        elif account_instrument:
            msg_in_position += (
                f"• {name} | {ticker} - {bold(account_instrument.direction)}\n"
            )
            msg_in_position += (
                f"   ЦЗ: {bold(get_exit_channel(instrument, account_instrument.direction))}\n\n"
            )

    return f"{msg_out_position}\n{msg_in_position}"
