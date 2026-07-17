from __future__ import annotations

from contextlib import AbstractAsyncContextManager
from typing import Any, Callable, Iterable, Protocol, Sequence


class WatchlistRepository(Protocol):
    session_factory: Callable[[], AbstractAsyncContextManager[Any]]

    async def list_instruments_by_ids(self, ids: list[str], session: Any) -> Sequence[Any]:
        ...

    async def upsert_account(
            self,
            *,
            account_id: str,
            name: str,
            check: bool,
            session: Any,
    ) -> None:
        ...

    async def upsert_instruments_bulk_data(
            self,
            items: Iterable[dict[str, Any]],
            session: Any,
    ) -> None:
        ...

    async def set_checked_bulk(
            self,
            ids: list[str],
            session: Any,
            check: bool = True,
    ) -> None:
        ...

    async def set_position_bulk(self, positions: list[dict[str, str]], session: Any) -> None:
        ...


class MarketDataClient(Protocol):
    async def get_days_candles_for_2_months(self, instrument_id: str) -> Any:
        ...

    async def get_futures_response(self, instruments_id: str) -> Any:
        ...
