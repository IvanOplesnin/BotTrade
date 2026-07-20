import asyncio
import datetime as dt
from datetime import datetime
from typing import Optional

import aiogram.exceptions
from aiogram import Bot, Dispatcher, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.fsm.storage.base import BaseStorage, DefaultKeyBuilder
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.storage.redis import RedisStorage
from aiogram.types import BotCommand
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from redis.asyncio import Redis

from bots.tg_bot.handlers.add_favorite_instruments import rout_add_favorites
from bots.tg_bot.handlers.info import info_rout
from bots.tg_bot.handlers.instrument_info import instr_info
from bots.tg_bot.handlers.remove_favorites import rout_remove_favorites
from bots.tg_bot.handlers.router import router
from bots.tg_bot.middlewares.deps import DepsMiddleware
from runtime.context import AppContext, build_app_context
from runtime.stream_handlers import (
    TelegramStreamHandlers,
    build_telegram_stream_handlers,
    register_telegram_stream_handlers,
)
from services.scheduler.scheduler import TZ_DEFAULT, parse_hhmm
from utils.logger import get_logger


class Service:

    def __init__(
            self,
            config_path: str,
            *,
            context: AppContext | None = None,
    ):
        self.portfolio_handler = None
        self.market_data_processor = None
        self.signal_notification_handler = None
        self.stream_handlers: TelegramStreamHandlers | None = None
        self.context = context or build_app_context(config_path)
        self.config_dict = self.context.config_dict
        self.config = self.context.config
        self.db_repo = self.context.db_repo
        self.redis = self.context.redis
        self.stream_bus = self.context.stream_bus
        self.tclient = self.context.tclient
        self.name_service = self.context.name_service
        self.portfolio_svc = self.context.portfolio_svc
        self.strategy_state_svc = self.context.strategy_state_svc
        self.market_candle_svc = self.context.market_candle_svc
        self.market_subscription_svc = self.context.market_subscription_svc
        self.strategy_subscription_svc = self.context.strategy_subscription_svc
        self.watchlist_svc = self.context.watchlist_svc
        self.portfolio_sync_svc = self.context.portfolio_sync_svc
        self.market_data_refresh_svc = self.context.market_data_refresh_svc

        self.scheduler: Optional[AsyncIOScheduler] = None
        tg_session = (
            AiohttpSession(proxy=self.config.tg_bot.proxy)
            if self.config.tg_bot.proxy
            else None
        )
        self.tg_bot: Bot = Bot(token=self.config.tg_bot.token,
                               session=tg_session,
                               default=DefaultBotProperties(parse_mode='HTML'))
        self.dp: Dispatcher = self._build_dispatcher()

        self.log = get_logger(self.__class__.__name__)

        # Планироващик
        # ---- планировщик ----
        self.tz = TZ_DEFAULT
        self.scheduler = AsyncIOScheduler(timezone=self.tz)
        self._tclient_running = False
        self._tclient_lock = asyncio.Lock()
        self._register_jobs_from_config()

    def _build_dispatcher(self) -> Dispatcher:
        dp = Dispatcher(storage=self._build_fsm_storage())
        dp.update.outer_middleware(DepsMiddleware(
            tclient=self.tclient,
            db=self.db_repo,
            name_service=self.name_service,
            redis=self.redis,
            portfolio_svc=self.portfolio_svc,
            watchlist_svc=self.watchlist_svc,
            market_subscription_svc=self.market_subscription_svc,
        ))
        dp.include_router(router=router)
        dp.include_router(router=rout_add_favorites)
        dp.include_router(router=rout_remove_favorites)
        dp.include_router(router=info_rout)
        dp.include_router(router=instr_info)
        return dp

    def _build_fsm_storage(self) -> BaseStorage:
        storage_cfg = self.config.telegram_storage
        if storage_cfg.backend == "memory":
            return MemoryStorage()

        redis_cfg = self.config.redis
        return RedisStorage(
            redis=Redis(
                host=redis_cfg.host,
                port=redis_cfg.port,
                db=redis_cfg.db,
                password=redis_cfg.password,
                ssl=redis_cfg.ssl,
                decode_responses=redis_cfg.decode_responses,
                socket_timeout=redis_cfg.socket_timeout,
                retry_on_timeout=redis_cfg.retry_on_timeout,
            ),
            key_builder=DefaultKeyBuilder(
                prefix=storage_cfg.key_prefix,
                with_bot_id=True,
            ),
            state_ttl=storage_cfg.state_ttl,
            data_ttl=storage_cfg.data_ttl,
        )

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
        plan = await self.strategy_subscription_svc.build_plan()
        await self.market_data_refresh_svc.refresh(
            update_notify=update_notify,
            subscription_plan=plan,
        )
        self.market_subscription_svc.apply_plan(plan)

    async def _run_polling_forever(self):
        backoff = 5
        while True:
            try:
                await self.dp.start_polling(self.tg_bot, close_bot_session=False)
                return
            except aiogram.exceptions.TelegramNetworkError as e:
                self.log.warning("Polling network error: %s — retry in",
                                 extra={"exception": e, "backoff": backoff})
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 120)
                self.dp = self._build_dispatcher()
                continue
            except Exception as e:
                self.log.exception("Polling crashed: %s — retry in %ss",
                                   extra={"exception": e, "backoff": backoff})
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 120)
                self.dp = self._build_dispatcher()
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

        await self._build_stream_handlers()
        self._register_stream_handlers()

        await self.redis.connect()
        await self.stream_bus.start()
        self.scheduler.start()
        if self.trading_time():
            await self._job_open_if_needed()

        commands = await self.collect_commands()
        try:
            await self.tg_bot.set_my_commands(commands)
        except aiogram.exceptions.TelegramNetworkError as e:
            self.log.warning("Telegram commands setup network error",
                             extra={"exception": e})
        else:
            self.log.info("Telegram commands configured")
        self.log.info("Started tg_bot")
        await self._run_polling_forever()

    async def _build_stream_handlers(self) -> None:
        self.stream_handlers = await build_telegram_stream_handlers(
            self.context,
            self.tg_bot,
        )
        self.market_data_processor = self.stream_handlers.market_data_processor
        self.portfolio_handler = self.stream_handlers.portfolio_handler
        self.signal_notification_handler = self.stream_handlers.signal_notification_handler

    def _register_stream_handlers(self) -> None:
        if self.stream_handlers is None:
            raise RuntimeError("Call _build_stream_handlers() before registration")
        register_telegram_stream_handlers(
            self.stream_bus,
            self.stream_handlers,
            consumers=self.config.runtime.telegram_consumers,
        )

    async def stop(self):
        self.scheduler.shutdown(wait=False)
        await self._ensure_tclient_stopped()
        await self.tg_bot.session.close()
        await self.stream_bus.stop()
        await self.redis.close()


def iter_message_handlers(router: Router):
    """Итерируемся по хендлерам message со всех роутеров (router + sub_routers)."""
    # Хендлеры, зарегистрированные на самом роутере
    for handler in router.message.handlers:
        yield handler

    # Рекурсивно обходим дочерние роутеры
    for sub in router.sub_routers:
        yield from iter_message_handlers(sub)
