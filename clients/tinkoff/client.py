from typing import Optional
import asyncio

import tinkoff.invest as ti
from tinkoff.invest.async_services import AsyncServices
from tinkoff.invest.market_data_stream.async_market_data_stream_manager import AsyncMarketDataStreamManager


class Client:

    def __init__(self, token: str, account_id: str = None, req_queue=None):
        self._token = token
        self._account_id = account_id
        self._client = ti.AsyncClient(token=token)
        self._req_queue = req_queue

        self._api: Optional[AsyncServices] = None
        self._stream: Optional[AsyncMarketDataStreamManager] = None

    async def get_accounts(self):
        async with self._client as client:
            get_accounts_response = await client.users.get_accounts()
            return get_accounts_response.accounts

    def set_account_id(self, account_id: str):
        self._account_id = account_id

    async def start(self):
        self._api = await self._client.__aenter__()
        self._stream = self._api.create_market_data_stream()
        asyncio.create_task(self._listen_stream())

    async def _listen_stream(self):
        if self.market_data_stream is None:
            return None



if __name__ == '__main__':
    import yaml
    import asyncio

    with open('config.yaml', 'r') as f:
        config = yaml.load(f, Loader=yaml.FullLoader)
        token = config['tinkoff-client']['token']

    TClient = Client(token)


    async def main():
        accs = await TClient.get_accounts()
        for acc in accs:
            print(acc.id)


    asyncio.run(main())
