from typing import Optional
import asyncio

import tinkoff.invest as ti
from tinkoff.invest.async_services import AsyncServices
from tinkoff.invest.market_data_stream.async_market_data_stream_manager import AsyncMarketDataStreamManager
from utils import logger


class TClient:

    def __init__(self, token: str, account_id: str = None, req_queue=None):
        self._token = token
        self._account_id = account_id
        self._client = ti.AsyncClient(token=token)
        self._req_queue = req_queue

        self._api: Optional[AsyncServices] = None
        self._stream_market: Optional[AsyncMarketDataStreamManager] = None
        self.market_stream_task: Optional[asyncio.Task] = None
        self.logger = logger.get_logger(self.__class__.__name__)

    async def get_accounts(self) -> list[ti.Account]:
        self.logger.debug('Getting accounts')

        if self._api is None:
            async with self._client as client:
                get_accounts_response = await client.users.get_accounts()
                return get_accounts_response.accounts
        else:
            get_accounts_response = await self._api.users.get_accounts()
            return get_accounts_response.accounts

    def set_account_id(self, account_id: str) -> None:
        self._account_id = account_id

    async def start(self) -> None:
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

        self.logger.info('Stopping client (stream_market_data and channel)')

    async def _listen_stream(self) -> None:
        backoff = 1
        while self._api is not None:
            try:
                if self._stream_market is None:
                    self._stream_market = self._api.create_market_data_stream()

                async for request in self._stream_market:
                    if self._req_queue is not None:
                        try:
                            self._req_queue.put_nowait(request)
                        except asyncio.QueueFull:
                            self.logger.warning("Queue full, drop request %s", request.__class__.__name__)
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


if __name__ == '__main__':
    import yaml
    import asyncio

    with open('config.yaml', 'r') as f:
        config = yaml.load(f, Loader=yaml.FullLoader)
        token = config['tinkoff-client']['token']


    async def main():
        t_client = TClient(token)
        await t_client.start()
        await asyncio.sleep(10)
        accounts = await t_client.get_accounts()
        print(accounts)
        await t_client.stop()


    asyncio.run(main())
