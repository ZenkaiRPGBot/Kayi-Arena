"""Bot & Dispatcher factory for Kayi Arena."""

from __future__ import annotations

import logging
import time
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware, Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand, TelegramObject, Update

from app.database import CharacterDatabase
from app.matches import MatchManager
from app.persistence import SqliteMatchStore
from app.telegram.config import BotConfig
from app.telegram.handlers import (
    build_admin_router,
    build_callbacks_router,
    build_commands_router,
    build_errors_router,
)
from app.telegram.ports import ProfileStatsProvider
from app.telegram.safe_api import answer_callback_safe, send_message_safe
from app.telegram.service import ArenaTelegramCoordinator

logger = logging.getLogger(__name__)

PUBLIC_BOT_COMMANDS: tuple[BotCommand, ...] = (
    BotCommand(command="start", description="Home menu"),
    BotCommand(command="arena", description="Start a draft battle or pick a universe"),
    BotCommand(command="game", description="View or recover your active match"),
    BotCommand(command="list", description="Browse the character catalogue"),
    BotCommand(command="profile", description="View your player profile"),
    BotCommand(command="leaderboard", description="View competitive leaderboards"),
    BotCommand(command="history", description="View your match history"),
    BotCommand(command="help", description="Read the Kayi Arena guide"),
    BotCommand(command="ping", description="Check bot responsiveness"),
)


class UpdateDedupMiddleware(BaseMiddleware):
    """Drops duplicate Telegram updates by update_id and records known chats."""

    def __init__(self, coordinator: ArenaTelegramCoordinator) -> None:
        self._coordinator = coordinator

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if isinstance(event, Update):
            if self._coordinator.is_duplicate_update(event.update_id):
                logger.debug("Skipping duplicate update_id=%s", event.update_id)
                return None
            msg = event.message or (event.callback_query.message if event.callback_query else None)
            if msg is not None:
                self._coordinator.register_chat(
                    msg.chat.id, msg.chat.type, getattr(msg.chat, "title", None)
                )
        t0 = time.perf_counter()
        try:
            return await handler(event, data)
        finally:
            self._coordinator.record_latency_ms((time.perf_counter() - t0) * 1000.0)


class MaintenanceMiddleware(BaseMiddleware):
    """Blocks non-admin gameplay commands & callbacks during maintenance mode."""

    def __init__(self, coordinator: ArenaTelegramCoordinator) -> None:
        self._coordinator = coordinator

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if not self._coordinator.is_maintenance_mode():
            return await handler(event, data)

        if isinstance(event, Update):
            user = (
                event.message.from_user
                if event.message
                else (event.callback_query.from_user if event.callback_query else None)
            )
            if user is not None and self._coordinator.config.is_admin(user.id):
                return await handler(event, data)
            if event.callback_query is not None:
                await answer_callback_safe(
                    event.callback_query,
                    "🔧 Kayi Arena is currently in maintenance mode.",
                    show_alert=True,
                )
                return None
            if event.message is not None and (event.message.text or "").startswith("/"):
                cmd = (event.message.text or "").split()[0].lower()
                if not cmd.startswith("/ping") and not cmd.startswith("/help"):
                    await send_message_safe(
                        self._coordinator.bot,
                        chat_id=event.message.chat.id,
                        text="🔧 <b>Maintenance Mode</b>\n\nKayi Arena is undergoing maintenance. Please try again shortly.",
                    )
                    return None
        t0 = time.perf_counter()
        try:
            return await handler(event, data)
        finally:
            self._coordinator.record_latency_ms((time.perf_counter() - t0) * 1000.0)


def create_bot(config: BotConfig) -> Bot:
    if not config.bot_token:
        raise ValueError("BOT_TOKEN is required to start Kayi Arena.")
    return Bot(
        token=config.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )


def create_dispatcher(
    *,
    bot: Bot,
    config: BotConfig,
    db: CharacterDatabase,
    manager: MatchManager | None = None,
    stats_provider: ProfileStatsProvider | None = None,
    store: SqliteMatchStore | None = None,
) -> tuple[Dispatcher, ArenaTelegramCoordinator]:
    mgr = manager or MatchManager(db, dataset_kind=config.dataset_kind, store=store)
    coordinator = ArenaTelegramCoordinator(
        bot=bot,
        config=config,
        db=db,
        manager=mgr,
        stats_provider=stats_provider,
        store=store,
    )
    dp = Dispatcher(storage=MemoryStorage())
    dp["coordinator"] = coordinator
    dp.update.outer_middleware(UpdateDedupMiddleware(coordinator))
    dp.update.outer_middleware(MaintenanceMiddleware(coordinator))
    dp.include_router(build_errors_router())
    dp.include_router(build_commands_router())
    dp.include_router(build_callbacks_router())
    dp.include_router(build_admin_router())
    return dp, coordinator


async def register_bot_commands(bot: Bot) -> None:
    await bot.set_my_commands(list(PUBLIC_BOT_COMMANDS))
