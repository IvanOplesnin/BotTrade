import hvac

class TokenStorage:
    def __init__(self, vault_address: str, role_id: str, secret_id: str):
        self._vault_address = vault_address
        self._role_id = role_id
        self._secret_id = secret_id

        self._client: hvac.Client = hvac.Client(url=self._vault_address)
        self._auth = self._client.auth.approle.login(role_id=self._role_id, secret_id=self._secret_id)
        self._client.token = self._auth["auth"]["client_token"]


    async def set_token(self, chat_id: str, token: str):
        await self._client.secrets.kv.v2.read