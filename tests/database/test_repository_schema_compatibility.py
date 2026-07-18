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
        "ALTER TABLE instruments ADD COLUMN IF NOT EXISTS type VARCHAR(16)",
        "ALTER TABLE instruments ADD COLUMN IF NOT EXISTS expiration_date TIMESTAMP WITH TIME ZONE",
        "ALTER TABLE account_instruments ADD COLUMN IF NOT EXISTS direction VARCHAR(16)",
    ]

