import asyncio
import functools
import inspect
from datetime import datetime as dt
import datetime
from typing import Optional

import tinkoff.invest as ti
from tinkoff.invest import AioRequestError
from tinkoff.invest.schemas import GetFavoriteGroupsRequest, FavoriteGroup, InstrumentResponse, FutureResponse, \
    InstrumentIdType, LastPrice
from tinkoff.invest.async_services import AsyncServices
from tinkoff.invest.market_data_stream.async_market_data_stream_manager import (
    AsyncMarketDataStreamManager
)

from core.domains.event_bus import StreamBus
from utils import logger

FAVORITES_ADD = ti.EditFavoritesActionType.EDIT_FAVORITES_ACTION_TYPE_ADD
FAVORITES_DELETE = ti.EditFavoritesActionType.EDIT_FAVORITES_ACTION_TYPE_DEL
FAVORITES_UNSPECIFIED = ti.EditFavoritesActionType.EDIT_FAVORITES_ACTION_TYPE_UNSPECIFIED


def require_api(method):
    """Гарантирует, что self._api доступен внутри вызова method.
    Если не поднят — поднимет временно и закроет после.
    """
    if not inspect.iscoroutinefunction(method):
        raise TypeError("@require_api можно вешать только на async-методы")

    @functools.wraps(method)
    async def wrapper(self, *args, **kwargs):
        if getattr(self, "_api", None) is not None:
            return await method(self, *args, **kwargs)

        async with ti.AsyncClient(token=self._token) as client:
            self._api = client
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
        self.portfolio_stream_task: Optional[asyncio.Task] = None

        self.logger = logger.get_logger(self.__class__.__name__)

        self.subscribes: dict[str, set[str]] = {}

    @require_api
    async def get_accounts(self) -> list[ti.Account]:
        self.logger.info('Getting accounts')
        get_accounts_response = await self._api.users.get_accounts()
        return get_accounts_response.accounts

    @require_api
    async def get_portfolio(self, account_id) -> ti.PortfolioResponse:
        self.logger.info('Getting portfolio')
        portfolio_response = await self._api.operations.get_portfolio(account_id=account_id)
        return portfolio_response

    @require_api
    async def _get_favorites_groups(self) -> list[FavoriteGroup]:
        self.logger.info('Getting favorite groups')
        response = await self._api.instruments.get_favorite_groups(
            request=GetFavoriteGroupsRequest()
        )
        return response.groups

    @require_api
    async def get_favorites_instruments(self) -> list[ti.GetFavoritesResponse]:
        self.logger.info('Getting favorites instruments')
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
    async def _get_candles(self, instrument_id: str,
                           interval: ti.CandleInterval,
                           start: datetime.datetime,
                           end: datetime.datetime) -> ti.GetCandlesResponse:
        self.logger.info('Getting candles_resp',
                         extra={'instrument_id': instrument_id, 'interval': interval, 'start': start, 'end': end})
        candles_response = await self._api.market_data.get_candles(
            instrument_id=instrument_id,
            interval=interval,
            from_=start,
            to=end
        )
        self.logger.info('Count Candles',
                         extra={'count': len(candles_response.candles), 'instrument_id': instrument_id,
                                'interval': interval,
                                'start': start, 'end': end})
        return candles_response

    @require_api
    async def get_days_candles_for_2_months(self, instrument_id: str) -> ti.GetCandlesResponse:
        self.logger.info('Getting days candles_resp for 2 months', extra={'instrument_id': instrument_id})

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
        self.logger.info('Getting name by id', extra={'instrument_id': instrument_id})
        response = await self._api.instruments.get_instrument_by(
            id_type=ti.InstrumentIdType.INSTRUMENT_ID_TYPE_UID,
            id=instrument_id
        )
        return response.instrument.name

    @require_api
    async def get_min_price_increment_amount(self, uid: str) -> Optional[
        ti.GetFuturesMarginResponse
    ]:
        try:
            self.logger.info('Get min_price_increment amount for futures',
                             extra={'uid': uid})
            margin_info = await self._api.instruments.get_futures_margin(
                instrument_id=uid
            )
            return margin_info
        except AioRequestError:
            self.logger.info('Not futures instrument')
            return None

    async def start(self, accounts: list[str]) -> None:
        self._client = ti.AsyncClient(token=self._token)
        self._api = await self._client.__aenter__()
        self._stream_market = None
        self.market_stream_task = asyncio.create_task(self._listen_stream())
        if accounts:
            self.portfolio_stream_task = asyncio.create_task(self._listen_portfolio_stream(
                accounts=accounts
            ))
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

        if self.portfolio_stream_task is not None:
            self.portfolio_stream_task.cancel()
            try:
                await self.portfolio_stream_task
            except asyncio.CancelledError:
                self.logger.info('Stream stopping')
            finally:
                self.portfolio_stream_task = None

        if self._api is not None:
            await self._client.__aexit__(None, None, None)
            self._api = None
        self._client = None

        self.logger.info('Stopping client (stream_market_data and channel)')

    @require_api
    async def edit_favorites_instruments(
            self, *instruments: str,
            group_id: str = None,
            action_type: ti.EditFavoritesActionType = FAVORITES_ADD
    ) -> ti.EditFavoritesResponse:

        list_instruments = [ti.EditFavoritesRequestInstrument(
            instrument_id=i
        ) for i in instruments]
        if group_id is None:
            groups_resp = await self._api.instruments.get_favorite_groups(
                request=GetFavoriteGroupsRequest()
            )
            group_id = next(g.group_id for g in groups_resp.groups if g.group_name == "Избранное")

        return await self._api.instruments.edit_favorites(
            instruments=list_instruments,
            group_id=group_id,
            action_type=action_type
        )

    async def _listen_stream(self) -> None:
        backoff = 1
        while self._api is not None:
            try:
                if self._stream_market is None:
                    self._stream_market = self._api.create_market_data_stream()
                    if self.subscribes:
                        for key, value in self.subscribes.items():
                            if key == 'last_price':
                                self.logger.info("Subscribing to instrument_last_price",
                                                 extra={'instruments_id': ", ".join(value)})
                                self.subscribe_to_instrument_last_price(*value)

                async for response in self._stream_market:
                    if self._stream_bus is not None:
                        try:
                            self.logger.info("Put response MarketDS",
                                             extra={"response": response.__class__.__name__})
                            await self._stream_bus.publish('market_data_stream', response)
                        except asyncio.QueueFull:
                            self.logger.warning("Queue full, drop response",
                                                extra={"response": response.__class__.__name__})
                    else:
                        self.logger.info("Received response:",
                                         extra={"response": response.__class__.__name__})
                backoff = 1

            except asyncio.CancelledError:
                raise
            except Exception as e:
                self.logger.error("Stream MarketDS error", extra={"exception": e})
                try:
                    if self._stream_market is not None:
                        self._stream_market.stop()
                finally:
                    self._stream_market = None
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 60)

    async def _listen_portfolio_stream(self, accounts: list[str]) -> None:
        backoff = 1
        while self._api is not None:
            try:
                self.logger.info("Start portfolio stream for accounts",
                                 extra={"account_id": ",".join(accounts)})
                async for response in self._api.operations_stream.portfolio_stream(
                        accounts=accounts,

                ):
                    if self._stream_bus is not None:
                        try:
                            self.logger.debug("Put Portfolio response",
                                              extra={"response": response.__class__.__name__})
                            await self._stream_bus.publish('portfolio_stream', response)
                        except asyncio.QueueFull:
                            self.logger.warning("Queue full, drop response",
                                                extra={"response": response.__class__.__name__})
                    else:
                        self.logger.debug("Received Portfolio response",
                                          extra={"response": response.__class__.__name__})
                backoff = 1

            except asyncio.CancelledError:
                raise
            except Exception as e:
                self.logger.error("Portfolio Stream error", {"exception": e})
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 60)

    async def recreate_portfolio_stream(self, accounts: list[str]) -> None:
        if self.portfolio_stream_task is not None:
            self.portfolio_stream_task.cancel()
            try:
                await self.portfolio_stream_task
            except asyncio.CancelledError:
                self.logger.info('Portfolio Stream stopping')
            finally:
                self.portfolio_stream_task = None
        if accounts:
            self.portfolio_stream_task = asyncio.create_task(self._listen_portfolio_stream(
                accounts=accounts
            ))

    @require_api
    async def get_futures_response(self, instruments_id: str) -> Optional[FutureResponse]:
        try:
            response = await self._api.instruments.future_by(id=instruments_id,
                                                             id_type=InstrumentIdType.INSTRUMENT_ID_TYPE_UID)
            return response
        except AioRequestError:
            self.logger.info('Not futures instrument')
            return None

    @require_api
    async def get_limit_requests(self):
        response = await self._api.users.get_user_tariff()
        return response

    def subscribe_to_instrument_last_price(self, *instruments_id: str) -> None:
        self.logger.debug("Subscribing to instrument_last_price",
                          extra={"instruments_ids": ", ".join(instruments_id)})
        if self.subscribes.get('last_price'):
            self.subscribes['last_price'].update(instruments_id)
        else:
            self.subscribes['last_price'] = set(instruments_id)

        self._stream_market.last_price.subscribe(
            instruments=[ti.LastPriceInstrument(instrument_id=i) for i in instruments_id]
        )

    def unsubscribe_to_instrument_last_price(self, *instruments_id: str):
        self.logger.debug("Unsubscribing to instrument_last_price %s",
                          extra={"instruments_ids": ", ".join(instruments_id)})
        for i_id in instruments_id:
            self.subscribes['last_price'].remove(i_id)

        self._stream_market.last_price.unsubscribe(
            instruments=[ti.LastPriceInstrument(instrument_id=i) for i in instruments_id]
        )

    @require_api
    async def get_last_price(self, instrument_id) -> Optional[LastPrice]:
        last_prices_response = await self._api.market_data.get_last_prices(
            instrument_id=[instrument_id]
        )
        result = None
        try:
            result = last_prices_response.last_prices[0]
        except IndexError:
            self.logger.error("Last price response is empty")

        return result

    @require_api
    async def get_info(self, instrument_id: str) -> InstrumentResponse:
        i_response = await self._api.instruments.get_instrument_by(
            id=instrument_id,
            id_type=InstrumentIdType.INSTRUMENT_ID_TYPE_UID
        )
        return i_response
