"""Secret-free global error handler for Kayi Arena."""

from __future__ import annotations

import logging

from aiogram import Router
from aiogram.types import ErrorEvent

from app.telegram.safe_api import answer_callback_safe, send_message_safe

logger = logging.getLogger(__name__)


async def on_error(event: ErrorEvent) -> bool:
    exc = event.exception
    logger.error("Unhandled update error: %s", type(exc).__name__, exc_info=exc)

    update = event.update
    if update.callback_query is not None:
        await answer_callback_safe(
            update.callback_query,
            "Something went wrong. Please try again.",
            show_alert=True,
        )
    elif update.message is not None:
        await send_message_safe(
            update.message.bot,
            chat_id=update.message.chat.id,
            text="⚠️ Something went wrong while processing that request.",
        )
    return True


def build_errors_router() -> Router:
    r = Router(name="kayi_arena_errors")
    r.error.register(on_error)
    return r
