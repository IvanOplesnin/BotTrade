from typing import Optional

from sqlalchemy import String, Boolean, ForeignKey, Float
from sqlalchemy.orm import DeclarativeBase, mapped_column, Mapped, relationship


class Base(DeclarativeBase):
    pass

    @classmethod
    def from_dict(cls, d: dict):
        return cls(**d)


class Account(Base):
    __tablename__ = "accounts"

    account_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    check: bool = mapped_column(Boolean, nullable=False, default=False)

    instruments: Mapped[list['Instrument']] = relationship(
        back_populates="account",
    )

class Instrument(Base):
    __tablename__ = 'instruments'

    instrument_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    account_id: Mapped[str] = mapped_column(ForeignKey('accounts.account_id'), nullable=False)
    ticker: Mapped[str] = mapped_column(String(16))
    in_position: Mapped[bool] = mapped_column(Boolean, default=False)
    direction: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    check: Mapped[bool] = mapped_column(Boolean, default=False)

    donchian_long_55: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    donchian_short_55: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    donchian_long_20: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    donchian_short_20: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    atr14: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    account: Mapped[Account] = relationship(
        back_populates="instruments",
    )


