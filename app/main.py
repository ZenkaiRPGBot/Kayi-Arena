"""Main polling entrypoint for Kayi Arena Telegram bot."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import replace
from pathlib import Path

from app.database import CharacterDatabase
from app.matches import MatchManager
from app.telegram.bot import create_bot, create_dispatcher, register_bot_commands
from app.telegram.config import BotConfig
from app.telegram.restart_notify import build_restart_notifier

logger = logging.getLogger(__name__)


async def run_bot() -> None:
    config = BotConfig.from_env()
    logging.basicConfig(
        level=getattr(logging, config.log_level, logging.INFO),
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )

    db_path = Path(config.db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    db = CharacterDatabase(db_path)
    bot = create_bot(config)

    try:
        me = await bot.get_me()
        if me.username:
            config = replace(config, bot_username=me.username)
        await register_bot_commands(bot)
    except Exception as exc:
        logger.warning("Startup metadata sync skipped: %s", type(exc).__name__)

    manager = MatchManager(db, dataset_kind=config.dataset_kind)
    dp, coordinator = create_dispatcher(bot=bot, config=config, db=db, manager=manager)

    notifier = build_restart_notifier(bot, config)
    asyncio.create_task(notifier.notify_once(), name="kayi-arena-restart-notify")

    try:
        await dp.start_polling(
            bot,
            allowed_updates=["message", "callback_query"],
            drop_pending_updates=config.drop_pending_updates,
        )
    finally:
        await coordinator.shutdown()
        await bot.session.close()
        db.close()


if __name__ == "__main__":
    asyncio.run(run_bot())
