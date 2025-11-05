from types import SimpleNamespace
import tinkoff.invest as ti

def quotation(units: int, nano: int) -> ti.Quotation:
    return ti.Quotation(units=units, nano=nano)

def last_price(uid: str, price: float) -> ti.LastPrice:
    # price -> Quotation
    units = int(price)
    nano = int(round((price - units) * 1_000_000_000))
    return ti.LastPrice(instrument_uid=uid, figi=None, price=quotation(units, nano))

def trade(uid: str, price: float, qty: int) -> ti.Trade:
    units = int(price)
    nano = int(round((price - units) * 1_000_000_000))
    return ti.Trade(instrument_uid=uid, figi=None, price=quotation(units, nano), quantity=qty)

def candle(uid: str, o, h, l, c):
    # Если понадобится — не используется в текущих тестах
    def q(v):
        u = int(v)
        n = int(round((v - u) * 1_000_000_000))
        return quotation(u, n)
    return ti.Candle(
        instrument_uid=uid, figi=None,
        open=q(o), high=q(h), low=q(l), close=q(c),
        volume=1, time=None, last_trade_ts=None, interval=ti.CandleInterval.CANDLE_INTERVAL_1_MIN
    )

def md_response_with_last_price(lp: ti.LastPrice):
    # У хэндлера в _extract — просто проверка на наличие атрибутов.
    # Поэтому SimpleNamespace с нужными полями полностью достаточен.
    return SimpleNamespace(
        subscribe_last_price_response=None,
        subscribe_trades_response=None,
        subscribe_info_response=None,
        subscribe_order_book_response=None,
        subscribe_candles_response=None,
        last_price=lp,
        trade=None,
        candle=None,
        orderbook=None,
        trading_status=None,
        ping=None,
        open_interest=None,
    )
