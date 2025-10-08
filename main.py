import asyncio

import yaml
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from poetry.repositories import Repository
from sqlalchemy.ext.asyncio import create_async_engine

from bots.tg_bot.handlers.router import router
from bots.tg_bot.middlewares.deps import DepsMiddleware
from clients.tinkoff.client import TClient


from config import Config


async def main():
    with open('config.yaml', 'r', encoding='utf-8') as f:
        config_dict = yaml.load(f, Loader=yaml.FullLoader)

    config: Config = Config(**config_dict)
    repository_database = Repository()



    bot = Bot(token=config.tg_bot.token, parse_mode="HTML")
    dp = Dispatcher(storage=MemoryStorage())

    tc_client = TClient(token=config.tinkoff_client.token)

    dp.update.outer_middleware(DepsMiddleware(tclient=tc_client))

    dp.include_router(router=router)

    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()

if __name__ == '__main__':
    asyncio.run(main())
