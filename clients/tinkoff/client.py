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
        self._stream: Optional[AsyncMarketDataStreamManager] = None
        self.logger = logger.get_logger(self.__class__.__name__)

    async def get_accounts(self):
        self.logger.debug('Getting accounts')
        async with self._client as client:
            get_accounts_response = await client.users.get_accounts()
            return get_accounts_response.accounts

    def set_account_id(self, account_id: str):
        self._account_id = account_id

    async def start(self):
        self._api = await self._client.__aenter__()
        self._stream = self._api.create_market_data_stream()
        asyncio.create_task(self._listen_stream())
        self.logger.info('Started client (stream_market_data and channel)')

    async def _listen_stream(self):
        if self._stream is None:
            self.logger.debug('Stream is None')
            return

        async for request in self._stream:
            if self._req_queue is not None:
                self._req_queue.put_nowait(request)
                self.logger.debug(f'Request put to queue: {request}')
            else:
                self.logger.debug(f'Received event: {request}')


if __name__ == '__main__':
    import yaml
    import asyncio

    with open('config.yaml', 'r') as f:
        config = yaml.load(f, Loader=yaml.FullLoader)
        token = config['tinkoff-client']['token']


    async def main():
        t_client = TClient(token)
        accs = await t_client.get_accounts()
        for acc in accs:
            print(acc.id)


    asyncio.run(main())
