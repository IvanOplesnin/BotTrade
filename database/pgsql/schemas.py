from __future__ import annotations
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class InstrumentIn(BaseModel):
    instrument_id: str = Field(..., max_length=40)
    ticker: str = Field(..., max_length=16)

    check: Optional[bool] = None
    to_notify: Optional[bool] = None

    donchian_long_55: Optional[float] = None
    donchian_short_55: Optional[float] = None
    donchian_long_20: Optional[float] = None
    donchian_short_20: Optional[float] = None
    atr14: Optional[float] = None

    last_update: Optional[datetime] = None


class InstrumentPatch(BaseModel):
    """Свободное обновление полей инструмента (partial update)."""
    ticker: Optional[str] = Field(None, max_length=16)
    check: Optional[bool] = None
    to_notify: Optional[bool] = None
    donchian_long_55: Optional[float] = None
    donchian_short_55: Optional[float] = None
    donchian_long_20: Optional[float] = None
    donchian_short_20: Optional[float] = None
    atr14: Optional[float] = None
    last_update: Optional[datetime] = None
