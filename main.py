import asyncio
from datetime import datetime
from typing import Optional

import aiogram.exceptions
import yaml
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.memory import MemoryStorage
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from bots.tg_bot.handlers.add_favorite_instruments import rout_add_favorites
from bots.tg_bot.handlers.check_notify import check_notify
from bots.tg_bot.handlers.remove_favorites import rout_remove_favorites
from bots.tg_bot.handlers.router import router
from bots.tg_bot.middlewares.deps import DepsMiddleware
from clients.tinkoff.client import TClient
from clients.tinkoff.name_service import NameService

from config import Config
from core.domains.event_bus import StreamBus
from core.schemas.stream_proc import MarketDataProcessor
from database.pgsql.repository import Repository
from database.redis.client import RedisClient
from services.historic_service.historic_service import IndicatorCalculator
from services.scheduler.scheduler import TZ_DEFAULT, parse_hhmm
from utils import is_updated_today
from utils.arg_parse import parser
from utils.logger import get_logger, setup_logging_from_dict


class Service:

    def __init__(self, config_path: str):
        self.config_dict: Optional[dict] = None
        self._get_config(config_path)
        self.config: Config = Config(**self.config_dict)
        self.db_repo: Repository = Repository(self.config.db_pgsql.address)
        self.stream_bus: StreamBus = StreamBus()
        self.tclient: TClient = TClient(token=self.config.tinkoff_client.token,
                                        stream_bus=self.stream_bus)
        self.redis = RedisClient(self.config.redis)
        self.name_service = NameService(self.redis, self.tclient, self.config.name_cache)

        self.scheduler: Optional[AsyncIOScheduler] = None
        self.tg_bot: Bot = Bot(token=self.config.tg_bot.token,
                               default=DefaultBotProperties(parse_mode='HTML'))
        self.dp: Dispatcher = Dispatcher(storage=MemoryStorage())
        self.dp.update.outer_middleware(DepsMiddleware(
            tclient=self.tclient,
            db=self.db_repo,
            name_service=self.name_service,
        ))
        self.dp.include_router(router=router)
        self.dp.include_router(router=rout_add_favorites)
        self.dp.include_router(router=rout_remove_favorites)
        self.dp.include_router(router=check_notify)
        self.log = get_logger(self.__class__.__name__)

        self.market_data_processor: MarketDataProcessor = MarketDataProcessor(
            self.tg_bot,
            chat_id=self.config.tg_bot.chat_id,
            db=self.db_repo,
            name_service=self.name_service,
            tclient=self.tclient
        )
        self.stream_bus.subscribe('market_data_stream', self.market_data_processor.execute)

        # Планироващик
        # ---- планировщик ----
        self.tz = TZ_DEFAULT  # при желании добавь в конфиг поле timezone
        self.scheduler = AsyncIOScheduler(timezone=self.tz)
        self._tclient_running = False
        self._tclient_lock = asyncio.Lock()
        self._register_jobs_from_config()

    def _get_config(self, path: str = 'config.yaml'):
        if not path:
            path = 'config.yaml'
        with open(path, 'r', encoding='utf-8') as f:
            config_dict = yaml.load(f, Loader=yaml.FullLoader)
        self.config_dict = config_dict

    def _register_jobs_from_config(self):
        start_t = parse_hhmm(self.config.scheduler_trading.start)
        close_t = parse_hhmm(self.config.scheduler_trading.close)

        # 2) начало: гарантированно включить
        self.scheduler.add_job(
            self._job_open_if_needed,
            CronTrigger(hour=start_t.hour, minute=start_t.minute),
            id="open_if_needed",
            replace_existing=True,
        )

        # 3) конец: отключить
        self.scheduler.add_job(
            self._job_close_and_stop,
            CronTrigger(hour=close_t.hour, minute=close_t.minute),
            id="close_and_stop",
            replace_existing=True,
        )

    async def _ensure_tclient_started(self):
        async with self._tclient_lock:
            if self._tclient_running:
                return
            await self.tclient.start()
            self._tclient_running = True
            await self._refresh_indicators_and_subscriptions(update_notify=True)

    async def _ensure_tclient_stopped(self):
        async with self._tclient_lock:
            if not self._tclient_running:
                return
            await self.tclient.stop()
            self._tclient_running = False

    async def _job_open_if_needed(self):
        await self._ensure_tclient_started()

    async def _job_close_and_stop(self):
        await self._ensure_tclient_stopped()

    async def _refresh_indicators_and_subscriptions(self, update_notify: bool = False):
        # то же, что твой init_service, но без «вечного» старта
        instruments = await self.db_repo.get_instruments()
        # Обновить индикаторы в БД
        tasks = []
        now = datetime.now(self.tz)
        for i in instruments:
            if not is_updated_today(i.last_update, now):
                tasks.append(self._recalc_and_update(i.instrument_id, i.ticker))
            if update_notify:
                tasks.append(self.db_repo.notify_to_true(i.instrument_id))
        await asyncio.gather(*tasks, return_exceptions=True)
        # Подписаться на активные
        if self.tclient.subscribes.get('last_price'):
            ids = [i.instrument_id for i in instruments if
                   (i.check and i.instrument_id not in self.tclient.subscribes['last_price'])]
        else:
            ids = [i.instrument_id for i in instruments if i.check]
        if ids:
            self.tclient.subscribe_to_instrument_last_price(*ids)

    async def _recalc_and_update(self, instrument_id: str, ticker: str):
        candles = await self.tclient.get_days_candles_for_2_months(instrument_id)
        indicators = IndicatorCalculator(ticker, candles).build_instrument_update()
        await self.db_repo.update_instrument_indicators(instrument_id, indicators)

    async def _run_polling_forever(self):
        backoff = 5
        while True:
            try:
                await self.dp.start_polling(self.tg_bot)
                backoff = 5  # если вышли «нормально», сброс
            except aiogram.exceptions.TelegramNetworkError as e:
                self.log.warning("Polling network error: %s — retry in %ss", e, backoff)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 120)
                continue
            except Exception as e:
                self.log.exception("Polling crashed: %s — retry in %ss", e, backoff)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 120)
                continue

    def trading_time(self):
        now = datetime.now(self.tz).time()
        start_t = parse_hhmm(self.config.scheduler_trading.start)
        close_t = parse_hhmm(self.config.scheduler_trading.close)
        return start_t <= now <= close_t

    async def start(self):
        await self.db_repo.create_db_if_exists()
        await self.stream_bus.start()
        await self.redis.connect()
        self.scheduler.start()
        if self.trading_time():
            await self._job_open_if_needed()

        await self._run_polling_forever()

    async def stop(self):
        self.scheduler.shutdown(wait=False)
        await self._ensure_tclient_stopped()
        await self.tg_bot.session.close()
        await self.stream_bus.stop()


async def main():
    args = parser.parse_args()
    with open(args.config, 'r', encoding='utf-8') as f:
        config_dict = yaml.load(f, Loader=yaml.FullLoader)

    setup_logging_from_dict(config_dict)
    service = Service(args.config)
    try:
        await service.start()
    finally:
        await service.stop()


if __name__ == '__main__':
    asyncio.run(main())
