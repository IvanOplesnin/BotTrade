from __future__ import annotations

from contextlib import AbstractAsyncContextManager
from typing import Any, Callable, Iterable, Protocol, Sequence

from application.dto import ActiveStrategyBinding


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
            update_ts: bool = True,
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

    async def list_positions_for_account(self, account_id: str, session: Any) -> Sequence[Any]:
        ...

    async def list_position_by_id(self, instrument_id: str, session: Any) -> Sequence[Any]:
        ...

    async def delete_account(self, account_id: str, session: Any) -> None:
        ...

    async def upsert_strategy_bindings(
            self,
            items: Iterable[dict[str, Any]],
            session: Any,
    ) -> None:
        ...

    async def set_strategy_bindings_enabled(
            self,
            *,
            instrument_ids: list[str],
            enabled: bool,
            session: Any,
            account_id: str | None = None,
    ) -> None:
        ...

    async def upsert_candles(self, items: Iterable[dict[str, Any]], session: Any) -> None:
        ...


class MarketDataClient(Protocol):
    async def get_days_candles_for_2_months(self, instrument_id: str) -> Any:
        ...

    async def get_futures_response(self, instruments_id: str) -> Any:
        ...

    async def get_instrument_type(self, instrument_id: str) -> str:
        ...


class MarketSignalRepository(Protocol):
    session_factory: Callable[[], AbstractAsyncContextManager[Any]]

    async def list_active_strategy_bindings_for_instrument(
            self,
            instrument_id: str,
            session: Any,
    ) -> Sequence[ActiveStrategyBinding]:
        ...

    async def get_instrument_with_positions(self, instrument_id: str, session: Any) -> Any:
        ...

    async def set_notify(self, uid: str, notify: bool, session: Any) -> None:
        ...

    async def add_strategy_signal(self, item: dict[str, Any], session: Any) -> None:
        ...


class PortfolioSyncRepository(Protocol):
    session_factory: Callable[[], AbstractAsyncContextManager[Any]]

    async def list_positions_for_account(self, account_id: str, session: Any) -> Sequence[Any]:
        ...

    async def list_instruments_by_ids(self, ids: list[str], session: Any) -> Sequence[Any]:
        ...

    async def upsert_instruments_bulk_data(
            self,
            items: Iterable[dict[str, Any]],
            session: Any,
            update_ts: bool = True,
    ) -> None:
        ...

    async def delete_all_positions_for_account(self, account_id: str, session: Any) -> None:
        ...

    async def delete_positions_bulk(
            self,
            account_id: str,
            instrument_ids: Iterable[str],
            session: Any,
    ) -> None:
        ...

    async def set_position_bulk(self, positions: list[dict[str, str]], session: Any) -> None:
        ...

    async def upsert_strategy_bindings(
            self,
            items: Iterable[dict[str, Any]],
            session: Any,
    ) -> None:
        ...

    async def set_strategy_bindings_enabled(
            self,
            *,
            instrument_ids: list[str],
            enabled: bool,
            session: Any,
            account_id: str | None = None,
    ) -> None:
        ...

    async def upsert_candles(self, items: Iterable[dict[str, Any]], session: Any) -> None:
        ...


class StrategyStateRepository(Protocol):
    session_factory: Callable[[], AbstractAsyncContextManager[Any]]

    async def list_active_strategy_bindings(self, session: Any) -> Sequence[ActiveStrategyBinding]:
        ...

    async def list_active_strategy_bindings_for_instruments(
            self,
            instrument_ids: list[str],
            session: Any,
    ) -> Sequence[ActiveStrategyBinding]:
        ...

    async def list_candles(
            self,
            *,
            instrument_id: str,
            timeframe: str,
            limit: int,
            session: Any,
    ) -> Sequence[Any]:
        ...

    async def upsert_strategy_state(self, item: dict[str, Any], session: Any) -> None:
        ...


class MarketDataRefreshRepository(Protocol):
    session_factory: Callable[[], AbstractAsyncContextManager[Any]]

    async def list_instruments(self, session: Any) -> Sequence[Any]:
        ...

    async def update_instrument_from_patch(
            self,
            instrument_id: str,
            patch: dict[str, Any],
            session: Any,
            touch_ts: bool = True,
    ) -> None:
        ...

    async def upsert_candles(self, items: Iterable[dict[str, Any]], session: Any) -> None:
        ...
