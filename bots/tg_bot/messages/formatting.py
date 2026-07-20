from __future__ import annotations

from decimal import Decimal, ROUND_FLOOR
from html import escape as html_escape
from typing import Optional

from clients.tinkoff.portfolio_svc import PortfolioOut

TELEGRAM_SAFE_MESSAGE_LIMIT = 3900
ERROR_TEXT_LIMIT = 1000


def fmt_number(value: Optional[float], nd: int = 2) -> str:
    return ("{0:,.%df}" % nd).format(value).replace(",", " ") if value is not None else "—"


def safe_error_text(error: Exception, limit: int = ERROR_TEXT_LIMIT) -> str:
    text = str(error)
    if len(text) > limit:
        text = f"{text[:limit]}..."
    return html_escape(text)


def split_message(text: str, limit: int = TELEGRAM_SAFE_MESSAGE_LIMIT) -> list[str]:
    """Split Telegram text preserving paragraphs first, then lines."""
    if limit <= 0:
        raise ValueError("limit must be positive")
    if len(text) <= limit:
        return [text]

    return _chunk_units(
        _split_keep_separator(text, "\n\n"),
        limit=limit,
        split_oversized=lambda unit: _chunk_units(
            _split_keep_separator(unit, "\n"),
            limit=limit,
            split_oversized=lambda line: _hard_split(line, limit),
        ),
    )


def _chunk_units(
        units: list[str],
        *,
        limit: int,
        split_oversized,
) -> list[str]:
    chunks: list[str] = []
    current = ""

    for unit in units:
        if not unit:
            continue

        if len(unit) > limit:
            if current:
                chunks.append(current)
                current = ""

            chunks.extend(split_oversized(unit))
            continue

        if len(current) + len(unit) > limit:
            chunks.append(current)
            current = unit
            continue

        current += unit

    if current:
        chunks.append(current)

    return chunks


def _split_keep_separator(text: str, separator: str) -> list[str]:
    parts = text.split(separator)
    units: list[str] = []
    for index, part in enumerate(parts):
        suffix = separator if index < len(parts) - 1 else ""
        unit = f"{part}{suffix}"
        if unit:
            units.append(unit)
    return units


def _hard_split(text: str, limit: int) -> list[str]:
    return [text[index:index + limit] for index in range(0, len(text), limit)]


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
