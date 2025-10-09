import tinkoff.invest as ti
from tinkoff.invest.utils import money_to_decimal as m2d, quotation_to_decimal as q2d

class HistoricCandleService:

    def __init__(self, ticker: str, candles: ti.GetCandlesResponse):
        self.ticker = ticker
        self.candles = candles


    def _atr(self):
        pass

    def _donchian_long(self, days: int):
        pass

    def _donchian_short(self, days: int):
        pass

    def get_data_for_55_donchian_channels(self):
        pass