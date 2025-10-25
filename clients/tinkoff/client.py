import asyncio
import functools
import inspect
from datetime import datetime as dt
import datetime
from typing import Optional

import tinkoff.invest as ti
from tinkoff.invest.schemas import GetFavoriteGroupsRequest, FavoriteGroup
from tinkoff.invest.async_services import AsyncServices
from tinkoff.invest.market_data_stream.async_market_data_stream_manager import (
    AsyncMarketDataStreamManager
)

from core.domains.event_bus import StreamBus
from utils import logger


def require_api(method):
    """Гарантирует, что self._api доступен внутри вызова method.
    Если не поднят — поднимет временно и закроет после.
    """
    if not inspect.iscoroutinefunction(method):
        raise TypeError("@require_api можно вешать только на async-методы")

    @functools.wraps(method)
    async def wrapper(self, *args, **kwargs):
        if getattr(self, "_api", None) is not None:
            # Клиент уже поднят где-то выше (например, в self.start())
            return await method(self, *args, **kwargs)

        # Ленивая сессия на один вызов
        async with ti.AsyncClient(token=self._token) as client:
            self._api = client  # чтобы method мог пользоваться self._api
            try:
                return await method(self, *args, **kwargs)
            finally:
                self._api = None

    return wrapper


class TClient:

    def __init__(self, token: str, account_id: str = None, stream_bus: StreamBus = None):
        self._token = token
        self._account_id = account_id
        self._client: Optional[ti.AsyncClient] = ti.AsyncClient(token=token)
        self._stream_bus = stream_bus

        self._api: Optional[AsyncServices] = None
        self._stream_market: Optional[AsyncMarketDataStreamManager] = None
        self.market_stream_task: Optional[asyncio.Task] = None
        self.logger = logger.get_logger(self.__class__.__name__)

        self.subscribes: dict[str, set[str]] = {}

    @require_api
    async def get_accounts(self) -> list[ti.Account]:
        self.logger.debug('Getting accounts')
        get_accounts_response = await self._api.users.get_accounts()
        return get_accounts_response.accounts

    @require_api
    async def get_portfolio(self, account_id) -> ti.PortfolioResponse:
        self.logger.debug('Getting portfolio')
        portfolio_response = await self._api.operations.get_portfolio(account_id=account_id)
        return portfolio_response

    @require_api
    async def _get_favorites_groups(self) -> list[FavoriteGroup]:
        self.logger.debug('Getting favorite groups')
        response = await self._api.instruments.get_favorite_groups(
            request=GetFavoriteGroupsRequest()
        )
        return response.groups

    @require_api
    async def get_favorites_instruments(self) -> list[ti.GetFavoritesResponse]:
        self.logger.debug('Getting favorites')
        groups = []
        response_groups = await self._get_favorites_groups()
        for group in response_groups:
            if group.size != 0:
                favorites_response = await self._api.instruments.get_favorites(
                    group_id=group.group_id)
                groups.append(favorites_response)
        return groups

    def set_account_id(self, account_id: str) -> None:
        self._account_id = account_id

    @require_api
    async def _get_candles(self, instrument_id: str, interval: ti.CandleInterval,
                           start: datetime, end: datetime) -> ti.GetCandlesResponse:
        self.logger.debug('Getting candles_resp %s', instrument_id)
        candles_response = await self._api.market_data.get_candles(
            instrument_id=instrument_id,
            interval=interval,
            from_=start,
            to=end
        )
        self.logger.debug('Count Candles: %s', len(candles_response.candles))
        return candles_response

    @require_api
    async def get_days_candles_for_2_months(self, instrument_id: str) -> ti.GetCandlesResponse:
        self.logger.debug('Getting days candles_resp for 2 months, %s', instrument_id)

        now = dt.now(datetime.timezone.utc)
        response = await self._get_candles(
            instrument_id=instrument_id,
            interval=ti.CandleInterval.CANDLE_INTERVAL_DAY,
            start=now - datetime.timedelta(days=100),
            end=now + datetime.timedelta(days=1),
        )
        return response

    @require_api
    async def get_name_by_id(self, instrument_id: str) -> str:
        self.logger.debug('Getting name by id: %s', instrument_id)
        response = await self._api.instruments.get_instrument_by(
            id_type=ti.InstrumentIdType.INSTRUMENT_ID_TYPE_UID,
            instrument_id=instrument_id
        )
        return response.instrument.name

    async def start(self) -> None:
        self._client = ti.AsyncClient(token=self._token)
        self._api = await self._client.__aenter__()
        self._stream_market = None
        self.market_stream_task = asyncio.create_task(self._listen_stream())
        self.logger.info('Started client (stream_market_data and channel)')

    async def stop(self) -> None:
        if self.market_stream_task is not None:
            self.market_stream_task.cancel()
            try:
                await self.market_stream_task
            except asyncio.CancelledError:
                self.logger.info('Stream stopping')
            finally:
                self.market_stream_task = None

        if self._stream_market is not None:
            self._stream_market.stop()
            self._stream_market = None

        if self._api is not None:
            await self._client.__aexit__(None, None, None)
            self._api = None
        self._client = None

        self.logger.info('Stopping client (stream_market_data and channel)')

    async def _listen_stream(self) -> None:
        backoff = 1
        while self._api is not None:
            try:
                if self._stream_market is None:
                    self._stream_market = self._api.create_market_data_stream()
                    if self.subscribes:
                        for key, value in self.subscribes.items():
                            if key == 'last_price':
                                self.logger.debug("Subscribing to instrument_last_price %s",
                                                  ", ".join(value))
                                self.subscribe_to_instrument_last_price(*value)

                async for request in self._stream_market:
                    if self._stream_bus is not None:
                        try:
                            self.logger.debug("Put request: %s", request.__class__.__name__)
                            await self._stream_bus.publish('market_data_stream', request)
                        except asyncio.QueueFull:
                            self.logger.warning("Queue full, drop request %s",
                                                request.__class__.__name__)
                    else:
                        self.logger.debug("Received request: %s", request.__class__.__name__)
                backoff = 1

            except asyncio.CancelledError:
                raise
            except Exception as e:
                self.logger.error("Stream error: %s", e)
                try:
                    if self._stream_market is not None:
                        self._stream_market.stop()
                finally:
                    self._stream_market = None
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 60)

    def subscribe_to_instrument_last_price(self, *instrument_id: str) -> None:
        self.logger.debug("Subscribing to instrument_last_price %s", ", ".join(instrument_id))
        if self.subscribes.get('last_price'):
            self.subscribes['last_price'].update(instrument_id)
        else:
            self.subscribes['last_price'] = set(instrument_id)

        self._stream_market.last_price.subscribe(
            instruments=[ti.LastPriceInstrument(instrument_id=i) for i in instrument_id]
        )

    def unsubscribe_to_instrument_last_price(self, *instruments_id: str):
        self.logger.debug("Unsubscribing to instrument_last_price %s", ", ".join(instruments_id))
        for i_id in instruments_id:
            self.subscribes['last_price'].remove(i_id)

        self._stream_market.last_price.unsubscribe(
            instruments=[ti.LastPriceInstrument(instrument_id=i) for i in instruments_id]
        )
