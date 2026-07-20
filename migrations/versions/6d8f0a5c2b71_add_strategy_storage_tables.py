"""add strategy storage tables

Revision ID: 6d8f0a5c2b71
Revises: 1c88b37275df
Create Date: 2026-07-20 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '6d8f0a5c2b71'
down_revision: Union[str, Sequence[str], None] = '1c88b37275df'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "candles",
        sa.Column("instrument_id", sa.String(length=40), nullable=False),
        sa.Column("timeframe", sa.String(length=16), nullable=False),
        sa.Column("time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("open", sa.Numeric(20, 10), nullable=False),
        sa.Column("high", sa.Numeric(20, 10), nullable=False),
        sa.Column("low", sa.Numeric(20, 10), nullable=False),
        sa.Column("close", sa.Numeric(20, 10), nullable=False),
        sa.Column("volume", sa.Integer(), nullable=True),
        sa.Column("is_complete", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(
            ["instrument_id"],
            ["instruments.instrument_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("instrument_id", "timeframe", "time"),
    )

    op.create_table(
        "strategy_bindings",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("strategy_code", sa.String(length=64), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("instrument_id", sa.String(length=40), nullable=False),
        sa.Column("account_id", sa.String(length=32), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("mode", sa.String(length=32), nullable=False),
        sa.Column(
            "params",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("timezone('utc', now())"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("timezone('utc', now())"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["accounts.account_id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["instrument_id"],
            ["instruments.instrument_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_strategy_bindings_instrument", "strategy_bindings", ["instrument_id"])
    op.create_index(
        "ix_strategy_bindings_strategy",
        "strategy_bindings",
        ["strategy_code", "version"],
    )

    op.create_table(
        "strategy_states",
        sa.Column("binding_id", sa.Integer(), nullable=False),
        sa.Column("timeframe", sa.String(length=16), nullable=False),
        sa.Column("instrument_id", sa.String(length=40), nullable=False),
        sa.Column("strategy_code", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column(
            "state_json",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("last_calculated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_market_event_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("timezone('utc', now())"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["binding_id"],
            ["strategy_bindings.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["instrument_id"],
            ["instruments.instrument_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("binding_id", "timeframe"),
    )
    op.create_index("ix_strategy_states_instrument", "strategy_states", ["instrument_id"])
    op.create_index("ix_strategy_states_strategy", "strategy_states", ["strategy_code"])

    op.create_table(
        "strategy_signals",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("binding_id", sa.Integer(), nullable=False),
        sa.Column("instrument_id", sa.String(length=40), nullable=False),
        sa.Column("strategy_code", sa.String(length=64), nullable=False),
        sa.Column("strategy_version", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=64), nullable=False),
        sa.Column("side", sa.String(length=16), nullable=True),
        sa.Column("price", sa.Numeric(20, 10), nullable=False),
        sa.Column("boundary", sa.Numeric(20, 10), nullable=True),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("event_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("timezone('utc', now())"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["binding_id"],
            ["strategy_bindings.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["instrument_id"],
            ["instruments.instrument_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_strategy_signals_binding", "strategy_signals", ["binding_id"])
    op.create_index(
        "ix_strategy_signals_instrument_time",
        "strategy_signals",
        ["instrument_id", "event_time"],
    )
    op.create_index(
        "ix_strategy_signals_strategy",
        "strategy_signals",
        ["strategy_code", "strategy_version"],
    )


def downgrade() -> None:
    op.drop_index("ix_strategy_signals_strategy", table_name="strategy_signals")
    op.drop_index("ix_strategy_signals_instrument_time", table_name="strategy_signals")
    op.drop_index("ix_strategy_signals_binding", table_name="strategy_signals")
    op.drop_table("strategy_signals")

    op.drop_index("ix_strategy_states_strategy", table_name="strategy_states")
    op.drop_index("ix_strategy_states_instrument", table_name="strategy_states")
    op.drop_table("strategy_states")

    op.drop_index("ix_strategy_bindings_strategy", table_name="strategy_bindings")
    op.drop_index("ix_strategy_bindings_instrument", table_name="strategy_bindings")
    op.drop_table("strategy_bindings")

    op.drop_table("candles")

