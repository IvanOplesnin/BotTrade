from __future__ import annotations

import pytest

from database.pgsql.repository import Repository

pytestmark = pytest.mark.asyncio


class FakeConnection:
    def __init__(self):
        self.statements: list[str] = []

    async def execute(self, statement):
        self.statements.append(str(statement))


async def test_legacy_schema_compatibility_adds_current_model_columns():
    conn = FakeConnection()

    await Repository.ensure_legacy_schema_compatibility(conn)

    assert conn.statements == [
        "ALTER TABLE instruments ADD COLUMN IF NOT EXISTS type VARCHAR(64)",
        "ALTER TABLE instruments ALTER COLUMN type TYPE VARCHAR(64)",
        "ALTER TABLE instruments ADD COLUMN IF NOT EXISTS expiration_date TIMESTAMP WITH TIME ZONE",
        "ALTER TABLE account_instruments ADD COLUMN IF NOT EXISTS direction VARCHAR(16)",
        """
        DELETE FROM strategy_bindings older
        USING strategy_bindings newer
        WHERE older.id < newer.id
          AND older.strategy_code = newer.strategy_code
          AND older.version = newer.version
          AND older.instrument_id = newer.instrument_id
          AND older.account_id IS NULL
          AND newer.account_id IS NULL
        """,
        """
        DELETE FROM strategy_bindings older
        USING strategy_bindings newer
        WHERE older.id < newer.id
          AND older.strategy_code = newer.strategy_code
          AND older.version = newer.version
          AND older.instrument_id = newer.instrument_id
          AND older.account_id = newer.account_id
          AND older.account_id IS NOT NULL
        """,
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_strategy_bindings_global
        ON strategy_bindings (strategy_code, version, instrument_id)
        WHERE account_id IS NULL
        """,
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_strategy_bindings_account
        ON strategy_bindings (strategy_code, version, instrument_id, account_id)
        WHERE account_id IS NOT NULL
        """,
    ]
