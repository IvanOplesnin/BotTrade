"""Compatibility re-exports for old imports.

New code should import from focused modules in bots.tg_bot.messages.
"""

from bots.tg_bot.messages.accounts import (
    text_add_account_message,
    text_delete_account_message,
)
from bots.tg_bot.messages.info import (
    info_database_message,
    info_notify_message,
    msg_portfolio_notify,
)
from bots.tg_bot.messages.instruments import (
    text_add_favorites_instruments,
    text_favorites_breakout,
    text_stop_long_position,
    text_stop_short_position,
    text_uncheck_favorites_instruments,
)
from bots.tg_bot.messages.static import HELP_TEXT, START_TEXT

__all__ = [
    "HELP_TEXT",
    "START_TEXT",
    "info_database_message",
    "info_notify_message",
    "msg_portfolio_notify",
    "text_add_account_message",
    "text_add_favorites_instruments",
    "text_delete_account_message",
    "text_favorites_breakout",
    "text_stop_long_position",
    "text_stop_short_position",
    "text_uncheck_favorites_instruments",
]
