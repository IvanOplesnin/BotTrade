import logging
from typing import Any

from aiogram import Bot

from application.dto import PositionLink
from application.portfolio_sync import PortfolioSyncService
from bots.tg_bot.messages.info import msg_portfolio_notify
from bots.tg_bot.sending import send_text
from clients.tinkoff.client import TClient
from clients.tinkoff.name_service import NameService
from database.pgsql.repository import Repository
from domain.stream_events import PortfolioSnapshotEvent


class PortfolioHandler:
    def __init__(self, bot: Bot, chat_id: int, db: Repository, name_service: NameService,
                 tclient: TClient,
                 portfolio_sync_svc: PortfolioSyncService | None = None):
        self._bot = bot
        self._chat_id = chat_id
        self.log = logging.getLogger(self.__class__.__name__)
        self._db = db
        self._name_service = name_service
        self._sync_svc = portfolio_sync_svc or PortfolioSyncService(db, tclient)

    async def execute(self, event: Any) -> None:
        self.log.debug("Executing %s", event.__class__.__name__)
        if not isinstance(event, PortfolioSnapshotEvent):
            self.log.debug("Unhandled portfolio event: %r", event)
            return
        await self._on_portfolio_snapshot(event)

    async def _on_portfolio_snapshot(self, portfolio: PortfolioSnapshotEvent) -> None:
        result = await self._sync_svc.sync(portfolio)
        if not result.added_positions and not result.deleted_instrument_ids:
            return

        await send_text(
            self._bot,
            chat_id=self._chat_id,
            text=await msg_portfolio_notify(
                _position_message_payloads(result.added_positions),
                set(result.deleted_instrument_ids),
                self._name_service,
            ),
        )


def _position_message_payloads(positions: list[PositionLink]) -> list[dict[str, str]]:
    return [
        {
            "account_id": position.account_id,
            "instrument_id": position.instrument_id,
            "direction": position.direction,
        }
        for position in positions
    ]
