"""Environment-driven configuration for Kayi Arena Telegram bot."""

from __future__ import annotations

import os
from dataclasses import dataclass

from app.scoring import DatasetKind

DEFAULT_DEVELOPER_URL = "https://t.me/qouba"
DEFAULT_UPDATES_URL = "https://t.me/KayiBots"
DEFAULT_SUPPORT_URL = "https://t.me/KayiBots"
DEFAULT_BOT_USERNAME = "KayiArenaBot"
BOT_BRAND_NAME = "Kayi Arena"


def _env_str(name: str, default: str = "") -> str:
    val = os.getenv(name, "").strip()
    return val if val else default


def _env_int(name: str, default: int = 0) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name, "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


@dataclass(frozen=True, slots=True)
class BotConfig:
    """Runtime configuration for Kayi Arena Telegram bot."""

    bot_token: str = ""
    bot_username: str = DEFAULT_BOT_USERNAME
    owner_id: int = 0
    log_channel_id: int = 0
    developer_url: str = DEFAULT_DEVELOPER_URL
    updates_url: str = DEFAULT_UPDATES_URL
    support_url: str = DEFAULT_SUPPORT_URL
    db_path: str = "data/kayi_arena.sqlite3"
    dataset_kind: DatasetKind = DatasetKind.PRODUCTION
    home_banner_ref: str = ""
    card_back_ref: str = ""
    drop_pending_updates: bool = True
    log_level: str = "INFO"

    @classmethod
    def from_env(cls) -> BotConfig:
        kind_raw = _env_str("ARENA_DATASET_KIND", DatasetKind.PRODUCTION.value).lower()
        try:
            dataset_kind = DatasetKind(kind_raw)
        except ValueError:
            dataset_kind = DatasetKind.PRODUCTION

        return cls(
            bot_token=_env_str("BOT_TOKEN", ""),
            bot_username=_env_str("BOT_USERNAME", DEFAULT_BOT_USERNAME).lstrip("@"),
            owner_id=_env_int("OWNER_ID", 0),
            log_channel_id=_env_int("LOG_CHANNEL_ID", 0),
            developer_url=_env_str("DEVELOPER_URL", DEFAULT_DEVELOPER_URL),
            updates_url=_env_str("UPDATES_URL", DEFAULT_UPDATES_URL),
            support_url=_env_str("SUPPORT_URL", DEFAULT_SUPPORT_URL),
            db_path=_env_str("ARENA_DB_PATH", "data/kayi_arena.sqlite3"),
            dataset_kind=dataset_kind,
            home_banner_ref=_env_str("HOME_BANNER_REF", ""),
            card_back_ref=_env_str("CARD_BACK_REF", ""),
            drop_pending_updates=_env_bool("DROP_PENDING_UPDATES", True),
            log_level=_env_str("LOG_LEVEL", "INFO").upper(),
        )
