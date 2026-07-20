"""add strategy binding unique indexes

Revision ID: b4a2d6c8e9f1
Revises: 6d8f0a5c2b71
Create Date: 2026-07-20 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "b4a2d6c8e9f1"
down_revision: Union[str, Sequence[str], None] = "6d8f0a5c2b71"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
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
