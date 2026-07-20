"""widen instrument type and ensure strategy indexes

Revision ID: c5d8f2a44b9e
Revises: b4a2d6c8e9f1
Create Date: 2026-07-20 20:40:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c5d8f2a44b9e"
down_revision: Union[str, Sequence[str], None] = "b4a2d6c8e9f1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "instruments",
        "type",
        existing_type=sa.String(length=16),
        type_=sa.String(length=64),
        existing_nullable=True,
    )
    op.execute(
        """
        DELETE FROM strategy_bindings older
        USING strategy_bindings newer
        WHERE older.id < newer.id
          AND older.strategy_code = newer.strategy_code
          AND older.version = newer.version
          AND older.instrument_id = newer.instrument_id
          AND older.account_id IS NULL
          AND newer.account_id IS NULL
        """
    )
    op.execute(
        """
        DELETE FROM strategy_bindings older
        USING strategy_bindings newer
        WHERE older.id < newer.id
          AND older.strategy_code = newer.strategy_code
          AND older.version = newer.version
          AND older.instrument_id = newer.instrument_id
          AND older.account_id = newer.account_id
          AND older.account_id IS NOT NULL
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_strategy_bindings_global
        ON strategy_bindings (strategy_code, version, instrument_id)
        WHERE account_id IS NULL
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_strategy_bindings_account
        ON strategy_bindings (strategy_code, version, instrument_id, account_id)
        WHERE account_id IS NOT NULL
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_strategy_bindings_account")
    op.execute("DROP INDEX IF EXISTS uq_strategy_bindings_global")
    op.alter_column(
        "instruments",
        "type",
        existing_type=sa.String(length=64),
        type_=sa.String(length=16),
        existing_nullable=True,
    )
