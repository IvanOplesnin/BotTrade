from __future__ import annotations

from clients.tinkoff.client import TClient
from database.pgsql.repository import Repository


def subscribe_last_prices_if_running(tclient: TClient, instrument_ids: list[str]) -> None:
    if instrument_ids and tclient.market_stream_task:
        tclient.subscribe_to_instrument_last_price(*instrument_ids)


def unsubscribe_last_prices_if_running(tclient: TClient, instrument_ids: list[str]) -> None:
    if instrument_ids and tclient.market_stream_task:
        tclient.unsubscribe_to_instrument_last_price(*instrument_ids)


async def recreate_portfolio_stream_from_db(tclient: TClient, db: Repository) -> None:
    if not tclient.portfolio_stream_task:
        return

    async with db.session_factory() as session:
        account_ids = [account.account_id for account in await db.list_accounts(session=session)]
    await tclient.recreate_portfolio_stream(account_ids)
