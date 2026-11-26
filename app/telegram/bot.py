"""Bot & Dispatcher factory for Kayi Arena."""

from __future__ import annotations

import logging
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
    build_callbacks_router,
    build_commands_router,
    build_errors_router,
)
from app.telegram.ports import ProfileStatsProvider
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
    """Drops duplicate Telegram updates by update_id."""

    def __init__(self, coordinator: ArenaTelegramCoordinator) -> None:
        self._coordinator = coordinator

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if isinstance(event, Update) and self._coordinator.is_duplicate_update(event.update_id):
            logger.debug("Skipping duplicate update_id=%s", event.update_id)
            return None
        return await handler(event, data)


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
    dp.include_router(build_errors_router())
    dp.include_router(build_commands_router())
    dp.include_router(build_callbacks_router())
    return dp, coordinator


async def register_bot_commands(bot: Bot) -> None:
    await bot.set_my_commands(list(PUBLIC_BOT_COMMANDS))
