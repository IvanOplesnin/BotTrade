from types import SimpleNamespace

import pytest

from clients.tinkoff.client import TClient
from clients.tinkoff.sdk import ti

pytestmark = pytest.mark.asyncio


class FakeUsers:
    def __init__(self):
        self.calls = []

    async def get_accounts(self):
        self.calls.append("get_accounts")
        return SimpleNamespace(accounts=["prod-account"])


class FakeOperations:
    def __init__(self):
        self.calls = []

    async def get_portfolio(self, account_id):
        self.calls.append(("get_portfolio", account_id))
        return SimpleNamespace(account_id=account_id, positions=[])


class FakeSandbox:
    def __init__(self):
        self.calls = []

    async def get_sandbox_accounts(self):
        self.calls.append("get_sandbox_accounts")
        return SimpleNamespace(accounts=["sandbox-account"])

    async def get_sandbox_portfolio(self, account_id):
        self.calls.append(("get_sandbox_portfolio", account_id))
        return SimpleNamespace(account_id=account_id, positions=[])

    async def open_sandbox_account(self, name=""):
        self.calls.append(("open_sandbox_account", name))
        return SimpleNamespace(account_id="sandbox-opened")

    async def sandbox_pay_in(self, account_id, amount):
        self.calls.append(("sandbox_pay_in", account_id, amount))
        return SimpleNamespace(balance=amount)

    async def post_sandbox_order(self, **kwargs):
        self.calls.append(("post_sandbox_order", kwargs))
        return SimpleNamespace(order_id=kwargs["order_id"])


def _fake_api():
    return SimpleNamespace(
        users=FakeUsers(),
        operations=FakeOperations(),
        sandbox=FakeSandbox(),
    )


async def test_prod_client_routes_accounts_and_portfolio_to_prod_services():
    client = TClient("token", sandbox=False)
    client._api = _fake_api()

    assert await client.get_accounts() == ["prod-account"]
    portfolio = await client.get_portfolio("ACC")

    assert portfolio.account_id == "ACC"
    assert client._api.users.calls == ["get_accounts"]
    assert client._api.operations.calls == [("get_portfolio", "ACC")]
    assert client._api.sandbox.calls == []


async def test_sandbox_client_routes_accounts_and_portfolio_to_sandbox_service():
    client = TClient("token", sandbox=True)
    client._api = _fake_api()

    assert await client.get_accounts() == ["sandbox-account"]
    portfolio = await client.get_portfolio("SBOX")

    assert portfolio.account_id == "SBOX"
    assert client._api.users.calls == []
    assert client._api.operations.calls == []
    assert client._api.sandbox.calls == [
        "get_sandbox_accounts",
        ("get_sandbox_portfolio", "SBOX"),
    ]


async def test_sandbox_order_helpers_call_sandbox_service():
    client = TClient("token", sandbox=True)
    client._api = _fake_api()

    opened = await client.open_sandbox_account("test")
    pay_in = await client.sandbox_pay_in("SBOX", units=10_000)
    order = await client.post_sandbox_order(
        account_id="SBOX",
        instrument_id="UID1",
        quantity=1,
        direction=ti.OrderDirection.ORDER_DIRECTION_BUY,
        order_type=ti.OrderType.ORDER_TYPE_MARKET,
        order_id="order-1",
    )

    assert opened.account_id == "sandbox-opened"
    assert pay_in.balance.units == 10_000
    assert order.order_id == "order-1"
    assert client._api.sandbox.calls[0] == ("open_sandbox_account", "test")
    assert client._api.sandbox.calls[1][0] == "sandbox_pay_in"
    assert client._api.sandbox.calls[2][0] == "post_sandbox_order"


async def test_sandbox_helpers_reject_prod_mode():
    client = TClient("token", sandbox=False)
    client._api = _fake_api()

    with pytest.raises(RuntimeError):
        await client.open_sandbox_account()


async def test_unsubscribe_last_price_is_idempotent_without_active_stream():
    client = TClient("token")
    client.subscribes["last_price"] = {"UID1"}

    client.unsubscribe_to_instrument_last_price("UID1", "UID2")
    client.unsubscribe_to_instrument_last_price("UID1", "UID2")

    assert client.subscribes["last_price"] == set()
