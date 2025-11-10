from typing import List, Optional

import tinkoff.invest as ti
from tinkoff.invest.utils import quotation_to_decimal as q2d


def q_to_float(q: ti.Quotation | float | int) -> float:
    """Tinkoff Quotation -> float (или вернуть как есть, если уже число)."""
    if isinstance(q, (float, int)):
        return float(q)
    return float(q.units) + float(q.nano) / 1_000_000_000.0


class IndicatorCalculator:
    """
    Упаковка «сырых» свечей с методами расчётов:
    - ATR(14) по Уайлдеру (Wilder's smoothing)
    - Donchian (верх/низ) для произвольного окна
    - Готовые дикты под апдейт таблиц Instrument / Position
    """

    def __init__(self, candles_resp: ti.GetCandlesResponse):
        completed = [c for c in candles_resp.candles if c.is_complete]
        self._candles: List[ti.HistoricCandle] = sorted(completed, key=lambda c: c.time)

        # подготовим кэш рядов
        self._high: Optional[List[float]] = None
        self._low: Optional[List[float]] = None
        self._close: Optional[List[float]] = None

    # ---------- базовые ряды ----------
    @property
    def _highs(self) -> List[float]:
        if self._high is None:
            self._high = [q2d(c.high) for c in self._candles]
        return self._high

    @property
    def _lows(self) -> List[float]:
        if self._low is None:
            self._low = [q2d(c.low) for c in self._candles]
        return self._low

    @property
    def _closes(self) -> List[float]:
        if self._close is None:
            self._close = [q2d(c.close) for c in self._candles]
        return self._close

    def _last_close(self) -> Optional[float]:
        return self._closes[-1] if self._closes else None

    @staticmethod
    def _last_window_max(xs: List[float], window: int) -> Optional[float]:
        return max(xs[-window:]) if len(xs) >= window else None

    @staticmethod
    def _last_window_min(xs: List[float], window: int) -> Optional[float]:
        return min(xs[-window:]) if len(xs) >= window else None

    # ---------- ATR (Wilder, n=14 по умолчанию) ----------
    def _atr(self, period: int = 14) -> Optional[float]:
        """
        Average True Range по Уайлдеру:
        TR_t = max( high_t - low_t, |high_t - close_{t-1}|, |low_t - close_{t-1}| )
        ATR_0 = average(TR_1..TR_period)
        ATR_t = (ATR_{t-1} * (period - 1) + TR_t) / period
        Возвращает ПОСЛЕДНЕЕ значение ATR.
        """
        highs, lows, closes = self._highs, self._lows, self._closes
        n = len(closes)
        if n < period + 1:
            return None  # нужно минимум period+1 свечей (есть prev close)

        # True Range для каждого бара, начиная со второго
        TR: List[float] = []
        for i in range(1, n):
            hi = highs[i]
            lo = lows[i]
            prev_c = closes[i - 1]
            tr = max(hi - lo, abs(hi - prev_c), abs(lo - prev_c))
            TR.append(tr)

        # Инициализация ATR средним TR первых `period` значений
        atr_prev = sum(TR[:period]) / period

        # Рекурсивное сглаживание Уайлдера для остального ряда
        for tr in TR[period:]:
            atr_prev = (atr_prev * (period - 1) + tr) / period

        return atr_prev

    def _atr_2(self, period: int = 14) -> Optional[float]:
        highs, lows, closes = self._highs, self._lows, self._closes
        n = len(closes)
        if n < period + 1:
            return None  # нужно минимум period+1 свечей (есть prev close)

        TR: List[float] = []
        for i in range(1, n):
            hi = highs[i]
            lo = lows[i]
            prev_c = closes[i - 1]
            tr = max(hi - lo, abs(hi - prev_c), abs(lo - prev_c))
            TR.append(tr)

        atr_prev = sum(TR[-period:]) / period
        return atr_prev

    # ---------- Готовые «срезы» под БД ----------
    def build_instrument_update(self) -> dict:
        """
        Возвращает dict, пригодный для апдейта Instrument:
        {
          'ticker': ...,
          'donchian_long_55': ...,
          'donchian_short_55': ...,
          'donchian_long_20': ...,
          'donchian_short_20': ...,
          'atr14': ...
        }
        """
        up55 = self._last_window_max(self._highs, 54)
        dn55 = self._last_window_min(self._lows, 54)
        up20 = self._last_window_max(self._highs, 19)
        dn20 = self._last_window_min(self._lows, 19)
        atr14 = self._atr(14)

        return {
            "donchian_long_55": up55,
            "donchian_short_55": dn55,
            "donchian_long_20": up20,
            "donchian_short_20": dn20,
            "atr14": atr14,
        }
