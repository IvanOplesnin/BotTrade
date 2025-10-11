import asyncio

import yaml
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.memory import MemoryStorage
from sqlalchemy.ext.asyncio import create_async_engine

from bots.tg_bot.handlers.router import router
from bots.tg_bot.middlewares.deps import DepsMiddleware
from clients.tinkoff.client import TClient


from config import Config
from database.pgsql.repository import Repository


async def processor_stream(queue):
    while True:
        request = await queue.get()
        print(request)

async def main():
    with open('config.yaml', 'r', encoding='utf-8') as f:
        config_dict = yaml.load(f, Loader=yaml.FullLoader)
    config: Config = Config(**config_dict)

    repository_database = Repository(
        url=config.db_pgsql.address,
    )
    await repository_database.create_db_if_exists()

    bot = Bot(token=config.tg_bot.token, default=DefaultBotProperties(parse_mode='HTML'))
    dp = Dispatcher(storage=MemoryStorage())

    queue = asyncio.Queue()
    tc_client = TClient(token=config.tinkoff_client.token, req_queue=queue)


    dp.update.outer_middleware(DepsMiddleware(tclient=tc_client, db=repository_database))

    dp.include_router(router=router)
    task_processor = asyncio.create_task(processor_stream(queue))
    try:
        await tc_client.start()
        await dp.start_polling(bot)
    finally:
        await tc_client.stop()
        await bot.session.close()
        task_processor.cancel()


if __name__ == '__main__':
    asyncio.run(main())
