from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import String, Boolean, Float, DateTime, ForeignKey, UniqueConstraint, Integer, Numeric, Index
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, mapped_column, Mapped, relationship
from sqlalchemy.sql.expression import text

from domain.instrument_links import tbank_instrument_link


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
    type: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
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

    expiration_date: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

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

    @property
    def link(self) -> str:
        return tbank_instrument_link(self.ticker, self.type)


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


class Candle(Base):
    __tablename__ = "candles"

    instrument_id: Mapped[str] = mapped_column(
        ForeignKey("instruments.instrument_id", ondelete="CASCADE"),
        primary_key=True,
    )
    timeframe: Mapped[str] = mapped_column(String(16), primary_key=True)
    time: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    open: Mapped[Decimal] = mapped_column(Numeric(20, 10), nullable=False)
    high: Mapped[Decimal] = mapped_column(Numeric(20, 10), nullable=False)
    low: Mapped[Decimal] = mapped_column(Numeric(20, 10), nullable=False)
    close: Mapped[Decimal] = mapped_column(Numeric(20, 10), nullable=False)
    volume: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    is_complete: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class StrategyBinding(Base):
    __tablename__ = "strategy_bindings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    strategy_code: Mapped[str] = mapped_column(String(64), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    instrument_id: Mapped[str] = mapped_column(
        ForeignKey("instruments.instrument_id", ondelete="CASCADE"),
        nullable=False,
    )
    account_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("accounts.account_id", ondelete="CASCADE"),
        nullable=True,
    )
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    mode: Mapped[str] = mapped_column(String(32), nullable=False, default="notify")
    params: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("timezone('utc', now())"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("timezone('utc', now())"),
    )

    __table_args__ = (
        Index("ix_strategy_bindings_instrument", "instrument_id"),
        Index("ix_strategy_bindings_strategy", "strategy_code", "version"),
        Index(
            "uq_strategy_bindings_global",
            "strategy_code",
            "version",
            "instrument_id",
            unique=True,
            postgresql_where=text("account_id IS NULL"),
        ),
        Index(
            "uq_strategy_bindings_account",
            "strategy_code",
            "version",
            "instrument_id",
            "account_id",
            unique=True,
            postgresql_where=text("account_id IS NOT NULL"),
        ),
    )


class StrategyState(Base):
    __tablename__ = "strategy_states"

    binding_id: Mapped[int] = mapped_column(
        ForeignKey("strategy_bindings.id", ondelete="CASCADE"),
        primary_key=True,
    )
    timeframe: Mapped[str] = mapped_column(String(16), primary_key=True)
    instrument_id: Mapped[str] = mapped_column(
        ForeignKey("instruments.instrument_id", ondelete="CASCADE"),
        nullable=False,
    )
    strategy_code: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="warming")
    state_json: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    last_calculated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    last_market_event_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("timezone('utc', now())"),
    )

    __table_args__ = (
        Index("ix_strategy_states_instrument", "instrument_id"),
        Index("ix_strategy_states_strategy", "strategy_code"),
    )


class StrategySignal(Base):
    __tablename__ = "strategy_signals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    binding_id: Mapped[int] = mapped_column(
        ForeignKey("strategy_bindings.id", ondelete="CASCADE"),
        nullable=False,
    )
    instrument_id: Mapped[str] = mapped_column(
        ForeignKey("instruments.instrument_id", ondelete="CASCADE"),
        nullable=False,
    )
    strategy_code: Mapped[str] = mapped_column(String(64), nullable=False)
    strategy_version: Mapped[int] = mapped_column(Integer, nullable=False)
    kind: Mapped[str] = mapped_column(String(64), nullable=False)
    side: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    price: Mapped[Decimal] = mapped_column(Numeric(20, 10), nullable=False)
    boundary: Mapped[Optional[Decimal]] = mapped_column(Numeric(20, 10), nullable=True)
    payload: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    event_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("timezone('utc', now())"),
    )

    __table_args__ = (
        Index("ix_strategy_signals_binding", "binding_id"),
        Index("ix_strategy_signals_instrument_time", "instrument_id", "event_time"),
        Index("ix_strategy_signals_strategy", "strategy_code", "strategy_version"),
    )
