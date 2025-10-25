from typing import Optional

from sqlalchemy import String, Boolean, Float, DateTime
from sqlalchemy.orm import DeclarativeBase, mapped_column, Mapped
from sqlalchemy.sql.expression import text


class Base(DeclarativeBase):
    pass

    @classmethod
    def from_dict(cls, d: dict):
        return cls(**d)


class Account(Base):
    __tablename__ = "accounts"

    account_id: Mapped[str] = mapped_column(String(32), primary_key=True, autoincrement=False)
    name: Mapped[str] = mapped_column(String(32), nullable=False)

    check: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class Instrument(Base):
    __tablename__ = 'instruments'

    instrument_id: Mapped[str] = mapped_column(String(40), primary_key=True, autoincrement=False)
    ticker: Mapped[str] = mapped_column(String(16))
    in_position: Mapped[bool] = mapped_column(Boolean, default=False)
    direction: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    check: Mapped[bool] = mapped_column(Boolean, default=False)
    to_notify: Mapped[bool] = mapped_column(Boolean, default=True)
    last_update: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        server_default=text("timezone('utc', now())"),
    )

    donchian_long_55: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    donchian_short_55: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    donchian_long_20: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    donchian_short_20: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    atr14: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    def __str__(self) -> str:
        return (
            f"\n{self.instrument_id} "
            f"({self.ticker};"
            f"check={self.check};"
            f"in_pos={self.in_position};"
            f"direction={self.direction});"
            f"notify=({self.to_notify})\n"
            f"LONG_55: {self.donchian_long_55}\n"
            f"SHORT_55: {self.donchian_short_55}\n"
            f"LONG_20: {self.donchian_long_20}\n"
            f"SHORT_20: {self.donchian_short_20}\n"
            f"ATR14: {self.atr14}\n"
        )
