"""account_instruments association table

Revision ID: 9c2cc03165e2
Revises: 462cc8d04ff1
Create Date: 2025-11-02 12:49:51.050646

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.sql.expression import text

# revision identifiers, used by Alembic.
revision: str = '9c2cc03165e2'
down_revision: Union[str, Sequence[str], None] = '462cc8d04ff1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1) Создаем таблицу-связку
    op.create_table(
        "account_instruments",
        sa.Column("account_id", sa.String(length=32), nullable=False),
        sa.Column("instrument_id", sa.String(length=40), nullable=False),
        sa.Column("direction", sa.String(length=16), nullable=True),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.account_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["instrument_id"], ["instruments.instrument_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("account_id", "instrument_id", name="pk_account_instruments"),
    )
    op.create_unique_constraint(
        "uq_account_instrument", "account_instruments", ["account_id", "instrument_id"]
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint("uq_account_instrument", "account_instruments", type_="unique")
    op.drop_table("account_instruments")
