"""Main entrypoint for Kayi Arena: lightweight HTTP server + webhook/polling."""

from __future__ import annotations

import asyncio
import logging
import signal
import sys
from dataclasses import replace
from pathlib import Path

from app.database import CharacterDatabase, bootstrap_naruto_database
from app.matches import MatchManager
from app.persistence import create_match_store
from app.telegram.bot import create_bot, create_dispatcher, register_bot_commands
from app.telegram.config import BotConfig
from app.telegram.restart_notify import build_restart_notifier
from app.telegram.web import build_health_app, start_http_server

logger = logging.getLogger(__name__)


async def run_bot() -> None:
    config = BotConfig.from_env()
    logging.basicConfig(
        level=getattr(logging, config.log_level, logging.INFO),
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        stream=sys.stdout,
        force=True,
    )
    logger.info(
        "Starting Kayi Arena (transport=%s, backend=%s, port=%d)",
        config.transport_mode,
        config.db_backend,
        config.port,
    )

    db_path = Path(config.db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    db = CharacterDatabase(db_path)

    snap_path = Path(config.bootstrap_snapshot_path) if config.bootstrap_snapshot_path else None
    boot_summary = bootstrap_naruto_database(
        db,
        dataset_kind=config.dataset_kind,
        snapshot_path=snap_path,
    )
    logger.info(
        "Naruto bootstrap complete: loaded=%d draft=%d held=%d testing=%s prod=%s",
        boot_summary.total_loaded,
        boot_summary.draft_count,
        boot_summary.held_count,
        boot_summary.published_testing_version,
        boot_summary.published_production_version,
    )

    store = create_match_store(config)
    bot = create_bot(config)

    manager = MatchManager(db, dataset_kind=config.dataset_kind, store=store)
    dp, coordinator = create_dispatcher(
        bot=bot, config=config, db=db, manager=manager, store=store
    )

    use_webhook = config.transport_mode == "webhook" and bool(config.webhook_url)
    health_status: dict[str, object] = {
        "transport_mode": "webhook" if use_webhook else "polling",
        "restored_matches": 0,
        "pending_challenges": 0,
    }
    health_app = build_health_app(
        extra_status=health_status,
        readiness_check=store.integrity_check,
        bot=bot if use_webhook else None,
        dp=dp if use_webhook else None,
        webhook_path=config.webhook_path if use_webhook else None,
        webhook_secret=config.webhook_secret,
    )
    runner, _site = await start_http_server(
        health_app, host=config.host, port=config.port
    )
    logger.info(
        "HTTP server listening on %s:%d (mode=%s)",
        config.host,
        config.port,
        "webhook" if use_webhook else "polling",
    )

    try:
        me = await asyncio.wait_for(bot.get_me(), timeout=10.0)
        if me.username:
            coordinator.config = replace(coordinator.config, bot_username=me.username)
        await asyncio.wait_for(register_bot_commands(bot), timeout=10.0)
    except Exception as exc:
        logger.warning("Startup metadata sync skipped: %s", type(exc).__name__)

    recovery_report = await coordinator.recover_on_startup()
    health_status["restored_matches"] = recovery_report.restored_matches
    health_status["pending_challenges"] = recovery_report.pending_challenges
    logger.info(
        "Startup recovery complete: restored=%d pending_chl=%d expired_chl=%d abandoned=%d errors=%d",
        recovery_report.restored_matches,
        recovery_report.pending_challenges,
        recovery_report.expired_challenges,
        recovery_report.abandoned_matches,
        len(recovery_report.recovery_errors),
    )

    notifier = build_restart_notifier(bot, coordinator.config)
    notify_task = asyncio.create_task(
        notifier.notify_once(recovery_report=recovery_report),
        name="kayi-arena-restart-notify",
    )

    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop_event.set)
        except NotImplementedError:
            pass

    try:
        if use_webhook:
            try:
                await asyncio.wait_for(
                    bot.set_webhook(
                        url=config.webhook_url,
                        secret_token=config.webhook_secret or None,
                        drop_pending_updates=config.drop_pending_updates,
                        allowed_updates=["message", "callback_query"],
                    ),
                    timeout=15.0,
                )
                logger.info("Webhook registered at %s", config.webhook_url)
            except Exception as exc:
                logger.warning("Webhook registration warning: %s", type(exc).__name__)
            await stop_event.wait()
        else:
            # Ensure no stale webhook causes a Telegram 409 Conflict during polling
            try:
                await bot.delete_webhook(drop_pending_updates=False)
            except Exception as exc:
                logger.warning("delete_webhook skipped: %s", type(exc).__name__)
            polling_task = asyncio.create_task(
                dp.start_polling(
                    bot,
                    allowed_updates=["message", "callback_query"],
                    drop_pending_updates=config.drop_pending_updates,
                )
            )
            stop_wait = asyncio.create_task(stop_event.wait())
            done, pending = await asyncio.wait(
                {polling_task, stop_wait}, return_when=asyncio.FIRST_COMPLETED
            )
            if stop_wait in done and not polling_task.done():
                await dp.stop_polling()
            for task in pending:
                task.cancel()
    finally:
        if not notify_task.done():
            notify_task.cancel()
        await coordinator.shutdown()
        await runner.cleanup()
        await bot.session.close()
        store.close()
        db.close()
        logger.info("Kayi Arena shut down cleanly.")


if __name__ == "__main__":
    asyncio.run(run_bot())
