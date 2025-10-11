from typing import Any

from tinkoff.invest import PortfolioResponse, FavoriteInstrument
from tinkoff.invest.utils import money_to_decimal as m2d
from tinkoff.invest.utils import quotation_to_decimal as q2d

from database.pgsql.models import Instrument

START_TEXT = (
    "<b>Привет!</b> Я <b>TradingTMasterBot</b> 🐍📈\n\n"
    "Помогаю работать с Тинькофф Инвестициями: добавляю аккаунт, "
    "получаю портфель, считаю индикаторы (Donchian, ATR) и присылаю обновления цен.\n\n"
    "Открой меню команд или напиши <code>/help</code>, чтобы посмотреть возможности."
)

HELP_TEXT = (
    "<b>Справка</b>\n\n"
    "<b>Основные команды:</b>\n"
    "• /start — приветствие и краткая информация о боте.\n"
    "• /help — эта справка.\n\n"
    "<b>Аккаунты:</b>\n"
    "• /add_account_check — выбрать и добавить аккаунт для отслеживания.\n"
    "• /remove_account_check — удалить ранее добавленный аккаунт.\n\n"
    "<b>Инструменты:</b>\n"
    "• /add_instruments_for_check — добавить избранные инструменты для отслеживания.\n"
    "• /uncheck_instruments — перестать отслеживать выбранные инструменты.\n\n"
    "<b>Что делает бот при добавлении аккаунта</b>:\n"
    "1) Загружает портфель и сохраняет инструменты в базу.\n"
    "2) Рассчитывает индикаторы: Donchian 55/20 и ATR(14).\n"
    "3) Подписывается на ленту цен (last_price) по инструментам из портфеля.\n\n"
    "<b>Подсказки:</b>\n"
    "• Если нужно остановить обработку текущей команды — нажми кнопку Отменить или начни заново.\n"
    "• Кнопки и подсказки появляются по ходу сценария — следуй инструкциям бота.\n\n"
    "<b>Технически</b>:\n"
    "— Бэк использует aiogram v3 и асинхронный клиент Тинькофф.\n"
    "— Данные хранятся в БД; вычисления индикаторов делаются по завершённым свечам.\n"
)



def text_add_account_message(indicators: list[dict[str, Any]]) -> str:
    return (f"Аккаунт успешно добавлен. Начинаем следить за инструментами:\n"
            f"{'\n'.join(f"{i['ticker']} - {i['direction']}" for i in indicators)}")


def text_delete_account_message(portfolio: PortfolioResponse) -> str:
    return (f"Аккаунт успешно удален. Удалены подписки на последние цены:\n"
            f"{'\n'.join(f"<b>{p.ticker}</b>" for p in portfolio.positions)}")


def text_add_favorites_instruments(instruments: list[Instrument]) -> str:
    return (f"Начинаем следить за инструментами:\n"
            f"{'\n'.join(f"✅ <b>{i.ticker}</b>" for i in instruments)}")


def text_uncheck_favorites_instruments(instruments: list[Instrument]) -> str:
    return (f"Перестаем следить за инструментами:\n"
            f"{'\n'.join(f"✅ <b>{i.ticker}</b>" for i in instruments)}")
