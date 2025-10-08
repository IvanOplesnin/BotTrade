from typing import Optional

from sqlalchemy import String, Boolean, ForeignKey, Float
from sqlalchemy.orm import DeclarativeBase, mapped_column, Mapped


class Base(DeclarativeBase):
    pass


class Instrument(Base):
    __tablename__ = 'instruments'

    instrument_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    ticker: Mapped[str] = mapped_column(String(16))
    in_position: Mapped[bool] = mapped_column(Boolean, default=False)
    check: Mapped[bool] = mapped_column(Boolean, default=False)

    donchian_long_55: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    donchian_short_55: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    atr14: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    current_price_pt: Mapped[Optional[float]] = mapped_column(Float, nullable=True)


class Position(Base):
    __tablename__ = 'positions'

    id: Mapped[int] = mapped_column(primary_key=True)

    instrument_id = mapped_column(ForeignKey(Instrument.instrument_id), unique=True)
    direction = mapped_column(String(16))

    donchian_long_20: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    donchian_short_20: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

