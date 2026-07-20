from __future__ import annotations

import logging
from types import SimpleNamespace
from typing import Optional

from aiogram import Bot
from aiogram.types import LinkPreviewOptions

from bots.tg_bot.messages.instruments import (
    text_favorites_breakout,
    text_stop_long_position,
    text_stop_short_position,
)
from bots.tg_bot.sending import send_text
from clients.tinkoff.name_service import NameService
from clients.tinkoff.portfolio_svc import PortfolioOut, PortfolioService
from clients.tinkoff.sdk import GetFuturesMarginResponse, q2d
from database.pgsql.repository import Repository
from domain.strategies import SignalKind
from domain.stream_events import StrategySignalCreatedEvent

STRATEGY_SIGNAL_TOPIC = "strategy_signals"


class TelegramSignalNotificationHandler:
    def __init__(
            self,
            bot: Bot,
            *,
            chat_id: int,
            db: Repository,
            name_service: NameService,
            tclient,
            portfolio_svc: PortfolioService,
    ):
        self._bot = bot
        self._chat_id = chat_id
        self._db = db
        self._name_service = name_service
        self._tclient = tclient
        self._portfolio_svc = portfolio_svc
        self._log = logging.getLogger(self.__class__.__name__)

    async def execute(self, event: StrategySignalCreatedEvent) -> None:
        if not isinstance(event, StrategySignalCreatedEvent):
            self._log.debug("Skip unsupported notification event: %r", event)
            return

        text = await build_strategy_signal_text(
            event,
            db=self._db,
            name_service=self._name_service,
            tclient=self._tclient,
            portfolio_svc=self._portfolio_svc,
        )
        if text is None:
            return

        await send_text(
            self._bot,
            chat_id=self._chat_id,
            text=text,
            link_preview_options=LinkPreviewOptions(is_disabled=True),
        )


async def build_strategy_signal_text(
        event: StrategySignalCreatedEvent,
        *,
        db: Repository,
        name_service: NameService,
        tclient,
        portfolio_svc: PortfolioService,
) -> Optional[str]:
    instrument = _instrument_from_event(event)
    kind = _signal_kind(event)
    if kind is None:
        return None

    if kind == SignalKind.STOP_LONG:
        return await text_stop_long_position(
            instrument,
            last_price=float(event.last_price),
            name_service=name_service,
        )
    if kind == SignalKind.STOP_SHORT:
        return await text_stop_short_position(
            instrument,
            last_price=float(event.last_price),
            name_service=name_service,
        )

    side = _signal_side(event)
    if side is None:
        return None

    margin_response = await tclient.get_min_price_increment_amount(uid=event.instrument_id)
    price_point_value = price_point(margin_response) if margin_response else None
    portfolios = await _portfolios(db, portfolio_svc)
    return await text_favorites_breakout(
        instrument,
        side,
        last_price=float(event.last_price),
        name_service=name_service,
        price_point_value=price_point_value,
        portfolios=portfolios,
    )


def price_point(margin_response: GetFuturesMarginResponse) -> float:
    return float(
        q2d(margin_response.min_price_increment_amount)
        / q2d(margin_response.min_price_increment)
    )


def _instrument_from_event(event: StrategySignalCreatedEvent) -> SimpleNamespace:
    return SimpleNamespace(
        instrument_id=event.instrument_id,
        ticker=event.ticker,
        type=event.instrument_type,
        donchian_long_55=event.indicators.get("donchian_long_55"),
        donchian_short_55=event.indicators.get("donchian_short_55"),
        donchian_long_20=event.indicators.get("donchian_long_20"),
        donchian_short_20=event.indicators.get("donchian_short_20"),
        atr14=event.indicators.get("atr14"),
    )


def _signal_kind(event: StrategySignalCreatedEvent) -> SignalKind | None:
    try:
        return SignalKind(event.signal_kind)
    except ValueError:
        logging.getLogger(__name__).warning(
            "Skip unknown strategy signal kind",
            extra={"kind": event.signal_kind, "instrument_id": event.instrument_id},
        )
        return None


def _signal_side(event: StrategySignalCreatedEvent) -> str | None:
    side = event.signal_side
    if side in {"long", "short"}:
        return side
    if event.signal_kind == SignalKind.BREAKOUT_LONG.value:
        return "long"
    if event.signal_kind == SignalKind.BREAKOUT_SHORT.value:
        return "short"
    return None


async def _portfolios(db: Repository, portfolio_svc: PortfolioService) -> list[PortfolioOut]:
    portfolios: list[PortfolioOut] = []
    async with db.session_factory() as session:
        accounts = await db.list_accounts(session)

    for account in accounts:
        portfolios.append(
            await portfolio_svc.get_portfolio(account.account_id, account.name)
        )
    return portfolios
