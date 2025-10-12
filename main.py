import asyncio

import yaml
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.memory import MemoryStorage

from bots.tg_bot.handlers.rout_add_favorite_instruments import rout_add_favorites
from bots.tg_bot.handlers.route_remove_favorites import rout_remove_favorites
from bots.tg_bot.handlers.router import router
from bots.tg_bot.middlewares.deps import DepsMiddleware
from clients.tinkoff.client import TClient

from config import Config
from core.domains.event_bus import StreamBus
from core.schemas.stream_processor import MarketDataProcessor
from database.pgsql.repository import Repository


async def processor_stream(queue):
    while True:
        request = await queue.get()
        print(request)

def init_stream_handlers(bus: StreamBus):
    pass


async def main():
    with open('config.yaml', 'r', encoding='utf-8') as f:
        config_dict = yaml.load(f, Loader=yaml.FullLoader)
    config: Config = Config(**config_dict)

    repository_database = Repository(
        url=config.db_pgsql.address,
    )
    await repository_database.create_db_if_exists()

    stream_bus = StreamBus()


    bot = Bot(token=config.tg_bot.token, default=DefaultBotProperties(parse_mode='HTML'))
    dp = Dispatcher(storage=MemoryStorage())

    queue = asyncio.Queue()
    tc_client = TClient(token=config.tinkoff_client.token, stream_bus=stream_bus)

    market_data_processor = MarketDataProcessor(
        bot,
        chat_id=config.tg_bot.chat_id,
        db=repository_database,
    )
    stream_bus.subscribe('market_data_stream', market_data_processor.execute)

    dp.update.outer_middleware(DepsMiddleware(tclient=tc_client, db=repository_database))

    dp.include_router(router=router)
    dp.include_router(router=rout_add_favorites)
    dp.include_router(router=rout_remove_favorites)
    task_processor = asyncio.create_task(processor_stream(queue))
    try:
        await tc_client.start()
        await stream_bus.start()
        await dp.start_polling(bot)
    finally:
        await tc_client.stop()
        await bot.session.close()
        await stream_bus.stop()
        task_processor.cancel()


if __name__ == '__main__':
    asyncio.run(main())
