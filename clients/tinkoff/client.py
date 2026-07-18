import functools
import inspect
from datetime import datetime as dt
import datetime
from typing import Any, Optional

from clients.tinkoff.sdk import (
    AioRequestError,
    AsyncServices,
    MoneyValue,
    OpenSandboxAccountResponse,
    OrderDirection,
    OrderType,
    PostOrderResponse,
    Quotation,
    SandboxPayInResponse,
)
from clients.tinkoff.sdk import (
    FutureResponse,
    GetFavoriteGroupsRequest,
    InstrumentIdType,
    LastPrice,
    sdk_instrument_name,
    sdk_text,
    ti,
)
from clients.tinkoff.streams import TinkoffStreamManager

from core.domains.message_bus import MessageBus
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

        async with self._new_client() as client:
            self._api = client
            try:
                return await method(self, *args, **kwargs)
            finally:
                self._api = None

    return wrapper


class TClient:

    def __init__(
            self,
            token: str,
            account_id: str = None,
            stream_bus: MessageBus = None,
            sandbox_token: str = None,
            sandbox: bool = False,
            app_name: str = None,
    ):
        self._token = token
        self._sandbox_token = sandbox_token
        self._sandbox = sandbox
        self._app_name = app_name
        self._account_id = account_id
        self._client: Optional[ti.AsyncClient] = None

        self._api: Optional[AsyncServices] = None

        self.logger = logger.get_logger(self.__class__.__name__)
        self._streams = TinkoffStreamManager(
            stream_bus=stream_bus,
            sandbox=sandbox,
            log=self.logger,
        )

    @property
    def is_sandbox(self) -> bool:
        return self._sandbox

    def _new_client(self) -> ti.AsyncClient:
        return ti.AsyncClient(
            token=self._token,
            sandbox_token=self._sandbox_token,
            app_name=self._app_name,
        )

    @property
    def market_stream_task(self):
        return self._streams.market_stream_task

    @property
    def portfolio_stream_task(self):
        return self._streams.portfolio_stream_task

    @property
    def subscribes(self) -> dict[str, set[str]]:
        return self._streams.subscribes

    @require_api
    async def get_accounts(self) -> list[ti.Account]:
        self.logger.info('Getting accounts')
        if self._sandbox:
            get_accounts_response = await self._api.sandbox.get_sandbox_accounts()
        else:
            get_accounts_response = await self._api.users.get_accounts()
        return get_accounts_response.accounts

    @require_api
    async def get_portfolio(self, account_id) -> ti.PortfolioResponse:
        self.logger.info('Getting portfolio')
        if self._sandbox:
            portfolio_response = await self._api.sandbox.get_sandbox_portfolio(
                account_id=account_id
            )
        else:
            portfolio_response = await self._api.operations.get_portfolio(account_id=account_id)
        return portfolio_response

    @require_api
    async def _get_favorites_groups(self):
        self.logger.info('Getting favorite groups')
        response = await self._api.instruments.get_favorite_groups(
            request=GetFavoriteGroupsRequest()
        )
        return response.groups

    @require_api
    async def get_favorites_instruments(self) -> list[ti.GetFavoritesResponse]:
        self.logger.info('Getting favorites instruments')
        responses = []
        response_groups = await self._get_favorites_groups()
        for group in response_groups:
            group_id = sdk_text(group, "group_id")
            group_size = getattr(group, "size", 0)
            if group_id and group_size:
                responses.append(
                    await self._api.instruments.get_favorites(group_id=group_id)
                )

        if not responses:
            responses.append(await self._api.instruments.get_favorites())

        return responses

    def set_account_id(self, account_id: str) -> None:
        self._account_id = account_id

    @require_api
    async def _get_candles(self, instrument_id: str,
                           interval: ti.CandleInterval,
                           start: datetime.datetime,
                           end: datetime.datetime) -> ti.GetCandlesResponse:
        self.logger.info('Getting candles_resp',
                         extra={'instrument_id': instrument_id, 'interval': interval, 'start': start, 'end': end})
        try:
            candles_response = await self._api.market_data.get_candles(
                instrument_id=instrument_id,
                interval=interval,
                from_=start,
                to=end
            )
        except AioRequestError:
            candles_response = await self._api.market_data.get_candles(
                figi=instrument_id,
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
        try:
            response = await self._api.instruments.get_instrument_by(
                id_type=ti.InstrumentIdType.INSTRUMENT_ID_TYPE_UID,
                id=instrument_id
            )
        except AioRequestError:
            response = await self._api.instruments.get_instrument_by(
                id_type=ti.InstrumentIdType.INSTRUMENT_ID_TYPE_FIGI,
                id=instrument_id
            )
        return sdk_instrument_name(response.instrument, default=instrument_id)

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
            try:
                margin_info = await self._api.instruments.get_futures_margin(
                    figi=uid
                )
                return margin_info
            except AioRequestError:
                self.logger.info('Not futures instrument')
                return None

    async def start(self, accounts: list[str]) -> None:
        self._client = self._new_client()
        self._api = await self._client.__aenter__()
        await self._streams.start(api=self._api, accounts=accounts)
        self.logger.info('Started client (stream_market_data and channel)')

    async def stop(self) -> None:
        await self._streams.stop()

        if self._api is not None and self._client is not None:
            await self._client.__aexit__(None, None, None)
        self._api = None
        self._client = None

        self.logger.info('Stopping client (stream_market_data and channel)')

    @require_api
    async def open_sandbox_account(self, name: str = "") -> OpenSandboxAccountResponse:
        self._ensure_sandbox()
        self.logger.info("Opening sandbox account", extra={"name": name})
        return await self._api.sandbox.open_sandbox_account(name=name)

    @require_api
    async def sandbox_pay_in(
            self,
            account_id: str,
            *,
            units: int,
            nano: int = 0,
            currency: str = "rub",
    ) -> SandboxPayInResponse:
        self._ensure_sandbox()
        amount = MoneyValue(currency=currency, units=units, nano=nano)
        self.logger.info("Sandbox pay in", extra={"account_id": account_id, "units": units})
        return await self._api.sandbox.sandbox_pay_in(
            account_id=account_id,
            amount=amount,
        )

    @require_api
    async def post_sandbox_order(
            self,
            *,
            account_id: str,
            instrument_id: str,
            quantity: int,
            direction: OrderDirection,
            order_type: OrderType = ti.OrderType.ORDER_TYPE_MARKET,
            price: Optional[Quotation] = None,
            order_id: str = "",
    ) -> PostOrderResponse:
        self._ensure_sandbox()
        self.logger.info(
            "Posting sandbox order",
            extra={
                "account_id": account_id,
                "instrument_id": instrument_id,
                "quantity": quantity,
                "direction": direction,
                "order_type": order_type,
            },
        )
        return await self._api.sandbox.post_sandbox_order(
            account_id=account_id,
            instrument_id=instrument_id,
            quantity=quantity,
            direction=direction,
            order_type=order_type,
            price=price,
            order_id=order_id,
        )

    def _ensure_sandbox(self) -> None:
        if not self._sandbox:
            raise RuntimeError("Sandbox operation is available only when tinkoff-client.sandbox=true")

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
            group_id = next(
                sdk_text(g, "group_id")
                for g in groups_resp.groups
                if sdk_text(g, "group_name") == "Избранное"
            )

        return await self._api.instruments.edit_favorites(
            instruments=list_instruments,
            group_id=group_id,
            action_type=action_type
        )

    async def recreate_portfolio_stream(self, accounts: list[str]) -> None:
        await self._streams.recreate_portfolio_stream(accounts)

    @require_api
    async def get_futures_response(self, instruments_id: str) -> Optional[FutureResponse]:
        try:
            response = await self._api.instruments.future_by(id=instruments_id,
                                                             id_type=InstrumentIdType.INSTRUMENT_ID_TYPE_UID)
            return response
        except AioRequestError:
            try:
                response = await self._api.instruments.future_by(
                    id=instruments_id,
                    id_type=InstrumentIdType.INSTRUMENT_ID_TYPE_FIGI,
                )
                return response
            except AioRequestError:
                self.logger.info('Not futures instrument')
                return None

    @require_api
    async def get_limit_requests(self):
        response = await self._api.users.get_user_tariff()
        return response

    def subscribe_to_instrument_last_price(self, *instruments_id: str) -> None:
        self._streams.subscribe_to_instrument_last_price(*instruments_id)

    def unsubscribe_to_instrument_last_price(self, *instruments_id: str):
        self._streams.unsubscribe_to_instrument_last_price(*instruments_id)

    @require_api
    async def get_last_price(self, instrument_id) -> Optional[LastPrice]:
        try:
            last_prices_response = await self._api.market_data.get_last_prices(
                instrument_id=[instrument_id]
            )
        except AioRequestError:
            last_prices_response = await self._api.market_data.get_last_prices(
                figi=[instrument_id]
            )
        result = None
        try:
            result = last_prices_response.last_prices[0]
        except IndexError:
            self.logger.error("Last price response is empty")

        return result

    @require_api
    async def get_info(self, instrument_id: str) -> Any:
        try:
            return await self._api.instruments.get_instrument_by(
                id=instrument_id,
                id_type=InstrumentIdType.INSTRUMENT_ID_TYPE_UID,
            )
        except AioRequestError:
            return await self._api.instruments.get_instrument_by(
                id=instrument_id,
                id_type=InstrumentIdType.INSTRUMENT_ID_TYPE_FIGI,
            )

    async def get_instrument_type(self, instrument_id: str) -> str:
        response = await self.get_info(instrument_id)
        return sdk_text(response.instrument, "instrument_type")
