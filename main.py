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
from services.historic_service.historic_service import IndicatorCalculator
from utils.arg_parse import parser


async def init_service(tclient: TClient, db: Repository):
    instruments = await db.get_instruments()
    ids = [i.instrument_id for i in instruments if i.check]
    # Обновить данные в Бд.
    for i in instruments:
        candles = await tclient.get_days_candles_for_2_months(i.instrument_id)
        indicators = IndicatorCalculator(i.ticker, candles).build_instrument_update()
        await db.update_instrument_indicators(i.instrument_id, indicators)
    # Подписаться на инструменты
    tclient.subscribe_to_instrument_last_price(*ids)

async def main():
    args = parser.parse_args()
    config_path = args.config if args.config else 'config.yaml'

    with open(config_path, 'r', encoding='utf-8') as f:
        config_dict = yaml.load(f, Loader=yaml.FullLoader)
    config: Config = Config(**config_dict)

    repository_database = Repository(
        url=config.db_pgsql.address,
    )
    await repository_database.create_db_if_exists()

    stream_bus = StreamBus()

    bot = Bot(token=config.tg_bot.token, default=DefaultBotProperties(parse_mode='HTML'))
    dp = Dispatcher(storage=MemoryStorage())

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

    try:
        await tc_client.start()
        await stream_bus.start()
        await init_service(tc_client, repository_database)
        await dp.start_polling(bot)
    finally:
        await tc_client.stop()
        await bot.session.close()
        await stream_bus.stop()


if __name__ == '__main__':
    asyncio.run(main())
