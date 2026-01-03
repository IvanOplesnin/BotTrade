import asyncio
import datetime as dt
from datetime import datetime
from typing import Optional

import aiogram.exceptions
import yaml
from aiogram import Bot, Dispatcher, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy.ext.asyncio import AsyncSession

from bots.tg_bot.handlers.add_favorite_instruments import rout_add_favorites
from bots.tg_bot.handlers.info import info_rout
from bots.tg_bot.handlers.instrument_info import instr_info
from bots.tg_bot.handlers.remove_favorites import rout_remove_favorites
from bots.tg_bot.handlers.router import router
from bots.tg_bot.middlewares.deps import DepsMiddleware
from clients.tinkoff.client import TClient
from clients.tinkoff.name_service import NameService

from config import Config
from core.domains.event_bus import StreamBus
from core.schemas.market_proc import MarketDataHandler
from core.schemas.portfolio import PortfolioHandler
from database.pgsql.repository import Repository
from database.redis.client import RedisClient
from services.historic_service.indicators import IndicatorCalculator
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
            redis=self.redis,
        ))
        self.dp.include_router(router=router)
        self.dp.include_router(router=rout_add_favorites)
        self.dp.include_router(router=rout_remove_favorites)
        self.dp.include_router(router=info_rout)
        self.dp.include_router(router=instr_info)

        self.log = get_logger(self.__class__.__name__)

        self.market_data_processor = MarketDataHandler(
            self.tg_bot,
            chat_id=self.config.tg_bot.chat_id,
            db=self.db_repo,
            name_service=self.name_service,
            tclient=self.tclient,
            redis=self.redis
        )
        self.portfolio_handler = PortfolioHandler(
            self.tg_bot,
            chat_id=self.config.tg_bot.chat_id,
            db=self.db_repo,
            name_service=self.name_service,
            tclient=self.tclient
        )
        self.stream_bus.subscribe('market_data_stream', self.market_data_processor.execute)
        self.stream_bus.subscribe('portfolio_stream', self.portfolio_handler.execute)
        # Планироващик
        # ---- планировщик ----
        self.tz = TZ_DEFAULT
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
        check_expiration_date = parse_hhmm(self.config.scheduler_trading.check_expiration_date)

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

        # 4) проверка даты экспирации
        self.scheduler.add_job(
            self._job_check_expiration_date,
            CronTrigger(hour=check_expiration_date.hour, minute=check_expiration_date.minute),
            id="check_expiration_date",
            replace_existing=True,
            timezone=self.tz,
        )

    async def _ensure_tclient_started(self):
        async with self._tclient_lock:
            if self._tclient_running:
                return
            async with self.db_repo.session_factory() as s:
                accounts = [a.account_id for a in await self.db_repo.list_accounts(session=s)]
            await self.tclient.start(accounts=accounts)
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

    async def _job_check_expiration_date(self):
        today = datetime.now(self.tz).date()
        delete_ins = []
        async with self.db_repo.session_factory() as s:
            instruments = await self.db_repo.list_instruments(s)
            deleted = 0
            for i in instruments:
                if not i.expiration_date:
                    continue
                exp_dt = i.expiration_date
                if getattr(exp_dt, "tzinfo", None) is not None:
                    exp_date = exp_dt.astimezone(self.tz).date()
                else:
                    exp_date = exp_dt.date()
                if exp_date < today + dt.timedelta(days=1):
                    await self.db_repo.delete_instrument(i.instrument_id, s)
                    delete_ins.append(i)
                    deleted += 1
            if deleted:
                await s.commit()

        if not delete_ins:
            return

        txt_msg = (f"Закончился срок действия {len(delete_ins)} инструментов:\n"
                   f"{'\n'.join(i.ticker for i in delete_ins)}")
        await self.tg_bot.send_message(
            self.config.tg_bot.chat_id,
            text=txt_msg
        )

    async def _refresh_indicators_and_subscriptions(self, update_notify: bool = False):
        # то же, что твой init_service, но без «вечного» старта
        async with self.db_repo.session_factory() as s:
            instruments = await self.db_repo.list_instruments(s)
            # Обновить индикаторы в БД
            tasks = []
            now = datetime.now(self.tz)
            for i in instruments:
                if not is_updated_today(i.last_update, now, self.tz):
                    self.log.debug("Refresh indicators for",
                                   extra={"instrument_name": await self.name_service.get_name(i.instrument_id),
                                          "instrument_id": i.instrument_id})
                    tasks.append(self._recalc_and_update(i.instrument_id, update_notify, s))
            await asyncio.gather(*tasks, return_exceptions=True)
            await s.commit()
        # Подписаться на активные
        if self.tclient.subscribes.get('last_price'):
            ids = [i.instrument_id for i in instruments if
                   (i.check and i.instrument_id not in self.tclient.subscribes['last_price'])]
        else:
            ids = [i.instrument_id for i in instruments if i.check]
        if ids:
            self.tclient.subscribe_to_instrument_last_price(*ids)

    async def _recalc_and_update(self, instrument_id: str, to_notify: bool, session: AsyncSession):
        candles = await self.tclient.get_days_candles_for_2_months(instrument_id)
        indicators = IndicatorCalculator(candles).build_instrument_update()
        if to_notify:
            indicators['to_notify'] = True
        await self.db_repo.update_instrument_from_patch(
            instrument_id=instrument_id,
            patch=indicators,
            touch_ts=True,
            session=session,
        )

    async def _run_polling_forever(self):
        backoff = 5
        while True:
            try:
                await self.dp.start_polling(self.tg_bot)
                backoff = 5  # если вышли «нормально», сброс
            except aiogram.exceptions.TelegramNetworkError as e:
                self.log.warning("Polling network error: %s — retry in",
                                 extra={"exception": e, "backoff": backoff})
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 120)
                continue
            except Exception as e:
                self.log.exception("Polling crashed: %s — retry in %ss",
                                   extra={"exception": e, "backoff": backoff})
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 120)
                continue

    def trading_time(self):
        now = datetime.now(self.tz).time()
        start_t = parse_hhmm(self.config.scheduler_trading.start)
        close_t = parse_hhmm(self.config.scheduler_trading.close)
        return start_t <= now <= close_t

    async def collect_commands(self) -> list[BotCommand]:
        commands: list[BotCommand] = []

        for handler in iter_message_handlers(self.dp):
            if "commands" not in handler.flags:
                continue

            for command in handler.flags["commands"]:
                commands.append(
                    BotCommand(
                        command=command.commands[0],
                        description=handler.callback.__doc__ or "No description available",
                    )
                )

        return commands

    async def start(self):
        await self.db_repo.create_schema_if_not_exists()
        await self.stream_bus.start()
        await self.redis.connect()
        self.scheduler.start()
        if self.trading_time():
            await self._job_open_if_needed()

        commands = await self.collect_commands()
        await self.tg_bot.set_my_commands(commands)
        await self._run_polling_forever()

    async def stop(self):
        self.scheduler.shutdown(wait=False)
        await self._ensure_tclient_stopped()
        await self.tg_bot.session.close()
        await self.stream_bus.stop()


def iter_message_handlers(router: Router):
    """Итерируемся по хендлерам message со всех роутеров (router + sub_routers)."""
    # Хендлеры, зарегистрированные на самом роутере
    for handler in router.message.handlers:
        yield handler

    # Рекурсивно обходим дочерние роутеры
    for sub in router.sub_routers:
        yield from iter_message_handlers(sub)


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
