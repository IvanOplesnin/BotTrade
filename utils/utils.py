import re
from typing import Final

TOKEN_RE: Final = re.compile(r"^t\.[A-Za-z0-9_\-]{60,512}$")  # запас по длине


class TokenError(ValueError):
    pass


def parse_token(token: str) -> bool:
    """
    Валидирует формат токена Tinkoff Invest: префикс t. и base64url-символы после него.
    Бросает TokenError с понятным текстом при ошибке.
    """
    if token is None:
        raise TokenError("Token is None")
    tok = token.strip()
    if not tok:
        raise TokenError("Token is empty")
    if not tok.startswith("t."):
        raise TokenError("Token must start with 't.'")
    if not TOKEN_RE.fullmatch(tok):
        raise TokenError("Token contains invalid characters or invalid length")


def mask_token(token: str, keep: int = 4) -> str:
    """
    Маскирует токен для логов: t.XXXX…last4
    """
    if not token:
        return "<empty>"
    head = "t."
    body = token[2:]
    if len(body) <= keep:
        return f"{head}{body}"
    return f"{head}{body[:keep]}…{body[-keep:]}"
