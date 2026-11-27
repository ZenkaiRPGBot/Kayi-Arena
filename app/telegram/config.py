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


def _env_float(name: str, default: float, *, minimum: float = 0.0) -> float:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        val = float(raw)
    except ValueError:
        return default
    return max(minimum, val)


def _env_int_tuple(name: str) -> tuple[int, ...]:
    raw = os.getenv(name, "").strip()
    if not raw:
        return ()
    result: list[int] = []
    for part in raw.split(","):
        item = part.strip()
        if not item:
            continue
        try:
            val = int(item)
        except ValueError:
            continue
        if val not in result:
            result.append(val)
    return tuple(result)


@dataclass(frozen=True, slots=True)
class BotConfig:
    """Runtime configuration for Kayi Arena Telegram bot."""

    bot_token: str = ""
    bot_username: str = DEFAULT_BOT_USERNAME
    owner_id: int = 0
    admin_ids: tuple[int, ...] = ()
    authorized_tester_ids: tuple[int, ...] = ()
    log_channel_id: int = 0
    arena_log_channel_id: int = 0
    developer_url: str = DEFAULT_DEVELOPER_URL
    updates_url: str = DEFAULT_UPDATES_URL
    support_url: str = DEFAULT_SUPPORT_URL
    db_backend: str = "sqlite"
    mongodb_uri: str = ""
    mongodb_database: str = "kayi_arena"
    db_path: str = "data/kayi_arena.sqlite3"
    match_db_path: str = "data/kayi_arena_state.sqlite3"
    restart_state_path: str = ""
    bootstrap_snapshot_path: str = "data/approved_naruto_snapshot.json"
    dataset_kind: DatasetKind = DatasetKind.PRODUCTION
    home_banner_ref: str = ""
    card_back_ref: str = ""
    media_channel_id: int = 0
    welcome_video_file_id: str = ""
    drop_pending_updates: bool = True
    log_level: str = "INFO"
    host: str = "0.0.0.0"
    port: int = 10000
    transport_mode: str = "polling"
    webhook_base_url: str = ""
    webhook_path: str = "/telegram/webhook"
    webhook_secret: str = ""
    enable_self_ping: bool = False
    ping_url: str = ""
    self_ping_initial_delay: float = 60.0
    self_ping_interval: float = 600.0
    self_ping_timeout: float = 10.0

    def all_admin_ids(self) -> tuple[int, ...]:
        ids = list(self.admin_ids)
        if self.owner_id and self.owner_id not in ids:
            ids.insert(0, self.owner_id)
        return tuple(ids)

    def is_admin(self, user_id: int | str) -> bool:
        try:
            uid = int(user_id)
        except (TypeError, ValueError):
            return False
        return uid != 0 and uid in self.all_admin_ids()

    def is_authorized_tester(self, user_id: int | str) -> bool:
        if self.is_admin(user_id):
            return True
        if not self.authorized_tester_ids:
            return self.dataset_kind is not DatasetKind.TEST
        try:
            uid = int(user_id)
        except (TypeError, ValueError):
            return False
        return uid != 0 and uid in self.authorized_tester_ids

    @property
    def webhook_url(self) -> str:
        base = self.webhook_base_url.rstrip("/")
        path = self.webhook_path if self.webhook_path.startswith("/") else f"/{self.webhook_path}"
        return f"{base}{path}" if base else ""

    @classmethod
    def from_env(cls) -> BotConfig:
        kind_raw = _env_str("ARENA_DATASET_KIND", DatasetKind.PRODUCTION.value).lower()
        try:
            dataset_kind = DatasetKind(kind_raw)
        except ValueError:
            dataset_kind = DatasetKind.PRODUCTION

        owner_id = _env_int("OWNER_ID", 0)
        admin_ids = _env_int_tuple("ADMIN_IDS")
        tester_ids = _env_int_tuple("AUTHORIZED_TESTER_IDS")
        webhook_base = _env_str("WEBHOOK_BASE_URL", "") or _env_str("RENDER_EXTERNAL_URL", "")
        mode_raw = _env_str("TRANSPORT_MODE", "polling").lower()
        transport_mode = "webhook" if mode_raw == "webhook" and webhook_base else "polling"
        render_external_url = _env_str("RENDER_EXTERNAL_URL", "")
        enable_self_ping = _env_bool("ENABLE_SELF_PING", bool(render_external_url))
        ping_url = _env_str("PING_URL", "")
        if not ping_url and enable_self_ping and render_external_url:
            ping_url = render_external_url.rstrip("/") + "/ping"

        mongodb_uri = _env_str("MONGODB_URI", "")
        db_backend_raw = _env_str("DB_BACKEND", "").lower()
        if db_backend_raw in {"sqlite", "mongodb"}:
            db_backend = db_backend_raw
        else:
            db_backend = "mongodb" if mongodb_uri else "sqlite"

        return cls(
            bot_token=_env_str("BOT_TOKEN", ""),
            bot_username=_env_str("BOT_USERNAME", DEFAULT_BOT_USERNAME).lstrip("@"),
            owner_id=owner_id,
            admin_ids=admin_ids,
            authorized_tester_ids=tester_ids,
            log_channel_id=_env_int("LOG_CHANNEL_ID", 0),
            arena_log_channel_id=_env_int("ARENA_LOG_CHANNEL_ID", 0),
            developer_url=_env_str("DEVELOPER_URL", DEFAULT_DEVELOPER_URL),
            updates_url=_env_str("UPDATES_URL", DEFAULT_UPDATES_URL),
            support_url=_env_str("SUPPORT_URL", DEFAULT_SUPPORT_URL),
            db_backend=db_backend,
            mongodb_uri=mongodb_uri,
            mongodb_database=_env_str("MONGODB_DATABASE", "kayi_arena"),
            db_path=_env_str("ARENA_DB_PATH", "data/kayi_arena.sqlite3"),
            match_db_path=_env_str("ARENA_STATE_DB_PATH", "data/kayi_arena_state.sqlite3"),
            restart_state_path=_env_str("RESTART_STATE_PATH", ""),
            bootstrap_snapshot_path=_env_str(
                "ARENA_BOOTSTRAP_SNAPSHOT_PATH", "data/approved_naruto_snapshot.json"
            ),
            dataset_kind=dataset_kind,
            home_banner_ref=_env_str("HOME_BANNER_REF", ""),
            card_back_ref=_env_str("CARD_BACK_REF", ""),
            media_channel_id=_env_int("MEDIA_CHANNEL_ID", 0),
            welcome_video_file_id=_env_str("WELCOME_VIDEO_FILE_ID", ""),
            drop_pending_updates=_env_bool("DROP_PENDING_UPDATES", True),
            log_level=_env_str("LOG_LEVEL", "INFO").upper(),
            host=_env_str("HOST", "0.0.0.0"),
            port=_env_int("PORT", 10000),
            transport_mode=transport_mode,
            webhook_base_url=webhook_base,
            webhook_path=_env_str("WEBHOOK_PATH", "/telegram/webhook"),
            webhook_secret=_env_str("WEBHOOK_SECRET", ""),
            enable_self_ping=enable_self_ping,
            ping_url=ping_url,
            self_ping_initial_delay=_env_float("SELF_PING_INITIAL_DELAY", 60.0, minimum=0.0),
            self_ping_interval=_env_float("SELF_PING_INTERVAL", 600.0, minimum=10.0),
            self_ping_timeout=_env_float("SELF_PING_TIMEOUT", 10.0, minimum=1.0),
        )
