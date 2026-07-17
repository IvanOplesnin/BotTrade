from __future__ import annotations

from decimal import Decimal, ROUND_FLOOR
from typing import Optional

from clients.tinkoff.portfolio_svc import PortfolioOut


def fmt_number(value: Optional[float], nd: int = 2) -> str:
    return ("{0:,.%df}" % nd).format(value).replace(",", " ") if value is not None else "—"


def split_message(text: str, limit: int = 3900) -> list[str]:
    chunks: list[str] = []
    current: list[str] = []
    current_len = 0

    for line in text.splitlines(keepends=True):
        line_len = len(line)

        if line_len > limit:
            if current:
                chunks.append("".join(current))
                current = []
                current_len = 0

            for index in range(0, line_len, limit):
                chunks.append(line[index:index + limit])

            continue

        if current_len + line_len > limit:
            chunks.append("".join(current))
            current = [line]
            current_len = line_len
        else:
            current.append(line)
            current_len += line_len

    if current:
        chunks.append("".join(current))

    return chunks


def calc_count_contracts(portfolio: PortfolioOut, atr: float, price_point: float) -> int:
    if not portfolio or not atr or not price_point:
        return 0

    atr_d = Decimal(str(atr))
    pp_d = Decimal(str(price_point))

    denom = atr_d * pp_d
    if denom <= 0:
        return 0

    profit = Decimal(0)
    percent = portfolio.expected_yield_percent
    if percent > 0:
        factor = Decimal(1) + percent / Decimal(100)
        initial_sum = portfolio.total_amount / factor
        profit = portfolio.total_amount - initial_sum
        if profit < 0:
            profit = Decimal(0)

    value = (portfolio.total_amount - profit) / (denom * 100)
    if value <= 0:
        return 0

    return int(value.to_integral_value(rounding=ROUND_FLOOR))
