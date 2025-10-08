from tinkoff.invest import PortfolioResponse
from tinkoff.invest.utils import money_to_decimal as m2d
from tinkoff.invest.utils import quotation_to_decimal as q2d

START_MESSAGE = ("Привет! я помогу тебе получать информацию по инструментам с биржи Тинькофф\n"
                 "Команды:\n"
                 "/set_account: Выбрать аккаунт, по которому будут отслеживаться твои позиции")


def add_account_message(portfolio: PortfolioResponse):
    return (f"Аккаунт успешно добавлен!\n"
            f"Баланс: {m2d(portfolio.total_amount_portfolio):.2f} руб.\n"
            f"Список позиций:\n"
            f"{'\n'.join(f"{p.ticker} - {q2d(p.quantity) * m2d(p.current_price):.2f}" 
                         for p in portfolio.positions)} руб.")
