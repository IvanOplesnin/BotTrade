from __future__ import annotations

import asyncio
from typing import Any, Sequence

from clients.tinkoff.name_service import NameService


async def text_add_account_message(
        indicators: Sequence[Any],
        name_service: NameService,
) -> str:
    uids = [item.instrument_id for item in indicators]
    names = await asyncio.gather(*(name_service.get_name(uid) for uid in uids))

    lines = []
    for item, name in zip(indicators, names):
        direction = item.direction
        direction_str = str(direction).upper() if direction is not None else "—"
        lines.append(f"✅ <b>{name}</b> — {direction_str}")

    body = "\n".join(lines) if lines else "нет инструментов."
    return "Аккаунт успешно добавлен. Начинаем следить за инструментами:\n" + body


async def text_delete_account_message(
        instrument_ids: Sequence[str],
        name_service: NameService,
) -> str:
    names = await asyncio.gather(*(name_service.get_name(uid) for uid in instrument_ids))

    lines = [f"❌ <b>{name}</b>" for name in names]
    body = "\n".join(lines) if lines else "подписок не было."
    return "Аккаунт успешно удалён. Удалены подписки на последние цены:\n" + body
