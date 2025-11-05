from typing import Optional

from sqlalchemy import String, Boolean, Float, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, mapped_column, Mapped, relationship
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

    instruments: Mapped[list["Instrument"]] = relationship(
        secondary="account_instruments",
        back_populates="accounts",
        lazy="selectin",
    )


class Instrument(Base):
    __tablename__ = 'instruments'

    instrument_id: Mapped[str] = mapped_column(String(40), primary_key=True, autoincrement=False)
    ticker: Mapped[str] = mapped_column(String(16))
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

    accounts: Mapped[list["Account"]] = relationship(
        secondary="account_instruments",
        back_populates="instruments",
        lazy="selectin",
    )

    def __str__(self) -> str:
        return (
            f"\n{self.instrument_id} "
            f"({self.ticker};"
            f"check={self.check};"
            f"notify=({self.to_notify})\n"
            f"LONG_55: {self.donchian_long_55}\n"
            f"SHORT_55: {self.donchian_short_55}\n"
            f"LONG_20: {self.donchian_long_20}\n"
            f"SHORT_20: {self.donchian_short_20}\n"
            f"ATR14: {self.atr14}\n"
        )


class AccountInstrument(Base):
    __tablename__ = "account_instruments"
    # Композитный ключ (account_id, instrument_id)
    account_id: Mapped[str] = mapped_column(
        ForeignKey("accounts.account_id", ondelete="CASCADE"), primary_key=True
    )
    instrument_id: Mapped[str] = mapped_column(
        ForeignKey("instruments.instrument_id", ondelete="CASCADE"), primary_key=True
    )

    # Факт позиции на ЭТОМ аккаунте по ЭТОМУ инструменту
    direction: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)

    # Индексы под типичные выборки
    __table_args__ = (
        UniqueConstraint("account_id", "instrument_id", name="uq_account_instrument"),
    )

    def __str__(self) -> str:
        return f"{self.direction}"