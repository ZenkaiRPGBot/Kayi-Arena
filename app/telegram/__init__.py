"""Kayi Arena — Module 6: Telegram UI & UX package."""

from app.telegram.bot import (
    PUBLIC_BOT_COMMANDS,
    UpdateDedupMiddleware,
    create_bot,
    create_dispatcher,
    register_bot_commands,
)
from app.telegram.callbacks import ParsedCallback, decode_cb, encode_cb
from app.telegram.config import BotConfig
from app.telegram.constants import RARITY_ICONS, ROLE_ICONS, ROLE_ORDER
from app.telegram.ports import ProfileStatsProvider, UnavailableStatsProvider
from app.telegram.restart_notify import RestartNotifier, build_restart_notifier
from app.telegram.service import ArenaTelegramCoordinator

__all__ = [
    "ArenaTelegramCoordinator",
    "BotConfig",
    "PUBLIC_BOT_COMMANDS",
    "ParsedCallback",
    "ProfileStatsProvider",
    "RARITY_ICONS",
    "ROLE_ICONS",
    "ROLE_ORDER",
    "RestartNotifier",
    "UnavailableStatsProvider",
    "UpdateDedupMiddleware",
    "build_restart_notifier",
    "create_bot",
    "create_dispatcher",
    "decode_cb",
    "encode_cb",
    "register_bot_commands",
]
