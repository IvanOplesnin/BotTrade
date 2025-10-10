from typing import Any

from tinkoff.invest import PortfolioResponse
from tinkoff.invest.utils import money_to_decimal as m2d
from tinkoff.invest.utils import quotation_to_decimal as q2d

START_MESSAGE = ("Привет! я помогу тебе получать информацию по инструментам с биржи Тинькофф\n"
                 "Команды:\n"
                 "/set_account: Выбрать аккаунт, по которому будут отслеживаться твои позиции")

def text_add_account_message(indicators: list[dict[str, Any]]) -> str:
    return (f"Аккаунт успешно добавлен. Начинаем следить за инструментами:\n"
            f"{'\n'.join(f"{i['ticker']} - {i['direction']}" for i in indicators)}")
