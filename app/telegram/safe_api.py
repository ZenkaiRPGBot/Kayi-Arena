"""Resilient Telegram Bot API wrappers for Kayi Arena.

Handles rate limits (`TelegramRetryAfter`), "message is not modified",
deleted messages, invalid media, missing permissions, expired callback queries,
bot removal (`TelegramForbiddenError`), and transient network errors.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from aiogram import Bot
from aiogram.enums import ParseMode
from aiogram.exceptions import (
    TelegramBadRequest,
    TelegramForbiddenError,
    TelegramNetworkError,
    TelegramRetryAfter,
)
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InputMediaPhoto, Message

logger = logging.getLogger(__name__)


def _is_not_modified_error(exc: TelegramBadRequest) -> bool:
    return "message is not modified" in str(exc).lower()


def _is_missing_message_error(exc: TelegramBadRequest) -> bool:
    msg = str(exc).lower()
    return (
        "message to edit not found" in msg
        or "message can't be edited" in msg
        or "message_id_invalid" in msg
    )


async def _call_with_retry(coro_factory: Any, *, max_attempts: int = 3) -> Any:
    for attempt in range(max_attempts):
        try:
            return await coro_factory()
        except TelegramRetryAfter as exc:
            wait = min(float(getattr(exc, "retry_after", 1.0)), 10.0)
            logger.warning("Telegram rate limit hit; retrying in %.2fs", wait)
            if attempt + 1 >= max_attempts:
                raise
            await asyncio.sleep(wait)
        except TelegramNetworkError as exc:
            logger.warning("Transient Telegram network error: %s", type(exc).__name__)
            if attempt + 1 >= max_attempts:
                raise
            await asyncio.sleep(0.5 * (attempt + 1))


async def answer_callback_safe(
    query: CallbackQuery,
    text: str | None = None,
    *,
    show_alert: bool = False,
) -> bool:
    try:
        await query.answer(text=text, show_alert=show_alert)
        return True
    except TelegramBadRequest as exc:
        logger.debug("Callback answer failed (likely expired): %s", exc)
        return False
    except Exception as exc:
        logger.warning("Unexpected error answering callback: %s", type(exc).__name__)
        return False


async def send_message_safe(
    bot: Bot,
    *,
    chat_id: int | str,
    text: str,
    reply_markup: InlineKeyboardMarkup | None = None,
    reply_to_message_id: int | None = None,
    disable_web_page_preview: bool = True,
) -> Message | None:
    try:
        return await _call_with_retry(
            lambda: bot.send_message(
                chat_id=chat_id,
                text=text,
                parse_mode=ParseMode.HTML,
                reply_markup=reply_markup,
                reply_to_message_id=reply_to_message_id,
                disable_web_page_preview=disable_web_page_preview,
            )
        )
    except TelegramForbiddenError:
        logger.info("Cannot send message to chat %s (bot removed or blocked)", chat_id)
        return None
    except TelegramBadRequest as exc:
        logger.warning("BadRequest sending message to %s: %s", chat_id, exc)
        return None
    except Exception as exc:
        logger.warning("Failed sending message to %s: %s", chat_id, type(exc).__name__)
        return None


async def edit_message_text_safe(
    bot: Bot,
    *,
    chat_id: int | str,
    message_id: int,
    text: str,
    reply_markup: InlineKeyboardMarkup | None = None,
    disable_web_page_preview: bool = True,
) -> bool:
    """Edit text message safely. Returns True if edited or already identical."""
    try:
        await _call_with_retry(
            lambda: bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=text,
                parse_mode=ParseMode.HTML,
                reply_markup=reply_markup,
                disable_web_page_preview=disable_web_page_preview,
            )
        )
        return True
    except TelegramBadRequest as exc:
        if _is_not_modified_error(exc):
            return True
        if _is_missing_message_error(exc):
            logger.info("Target message %s in chat %s missing/uneditable", message_id, chat_id)
            return False
        logger.warning("BadRequest editing message %s in %s: %s", message_id, chat_id, exc)
        return False
    except TelegramForbiddenError:
        logger.info("Cannot edit message in chat %s (bot removed or blocked)", chat_id)
        return False
    except Exception as exc:
        logger.warning("Failed editing message %s in %s: %s", message_id, chat_id, type(exc).__name__)
        return False


async def send_photo_or_text_safe(
    bot: Bot,
    *,
    chat_id: int | str,
    photo: str | None,
    caption: str,
    reply_markup: InlineKeyboardMarkup | None = None,
    fallback_photo: str | None = None,
) -> tuple[Message | None, bool]:
    """Send a photo card, falling back cleanly to fallback_photo or plain text.

    Returns (Message | None, is_photo_message).
    """
    candidates = [ref for ref in (photo, fallback_photo) if ref]
    for ref in candidates:
        try:
            msg = await _call_with_retry(
                lambda r=ref: bot.send_photo(
                    chat_id=chat_id,
                    photo=r,
                    caption=caption,
                    parse_mode=ParseMode.HTML,
                    reply_markup=reply_markup,
                )
            )
            return msg, True
        except TelegramForbiddenError:
            logger.info("Cannot send photo to chat %s (bot removed or blocked)", chat_id)
            return None, False
        except TelegramBadRequest as exc:
            logger.warning("Invalid media ref %r for chat %s: %s", ref, chat_id, exc)
            continue
        except Exception as exc:
            logger.warning("Failed sending photo to %s: %s", chat_id, type(exc).__name__)
            continue

    msg = await send_message_safe(
        bot,
        chat_id=chat_id,
        text=caption,
        reply_markup=reply_markup,
    )
    return msg, False


async def replace_text_with_photo_card_safe(
    bot: Bot,
    *,
    chat_id: int | str,
    old_message_id: int,
    photo: Any,
    caption: str,
    reply_markup: InlineKeyboardMarkup | None = None,
    fallback_photo: Any | None = None,
) -> tuple[Message | None, bool]:
    """Upgrade a text card into a photo card by sending the photo and deleting the old text."""
    sent, is_photo = await send_photo_or_text_safe(
        bot,
        chat_id=chat_id,
        photo=photo,
        caption=caption,
        reply_markup=reply_markup,
        fallback_photo=fallback_photo,
    )
    if sent is not None and is_photo:
        try:
            await bot.delete_message(chat_id=chat_id, message_id=old_message_id)
        except Exception:
            pass
    return sent, is_photo


async def edit_card_message_safe(
    bot: Bot,
    *,
    chat_id: int | str,
    message_id: int,
    is_photo: bool,
    photo: Any | None,
    caption: str,
    reply_markup: InlineKeyboardMarkup | None = None,
    fallback_photo: Any | None = None,
) -> tuple[bool, bool]:
    """Update an existing card message (photo or text) without losing controls.

    Returns (succeeded, still_is_photo).
    """
    if is_photo:
        media_ref = photo or fallback_photo
        if media_ref:
            try:
                await _call_with_retry(
                    lambda: bot.edit_message_media(
                        chat_id=chat_id,
                        message_id=message_id,
                        media=InputMediaPhoto(
                            media=media_ref,
                            caption=caption,
                            parse_mode=ParseMode.HTML,
                        ),
                        reply_markup=reply_markup,
                    )
                )
                return True, True
            except TelegramBadRequest as exc:
                if _is_not_modified_error(exc):
                    return True, True
                if _is_missing_message_error(exc):
                    return False, True
                logger.warning("edit_message_media failed (%s); falling back to caption edit", exc)

        # Fallback: edit caption only on existing photo message
        try:
            await _call_with_retry(
                lambda: bot.edit_message_caption(
                    chat_id=chat_id,
                    message_id=message_id,
                    caption=caption,
                    parse_mode=ParseMode.HTML,
                    reply_markup=reply_markup,
                )
            )
            return True, True
        except TelegramBadRequest as exc:
            if _is_not_modified_error(exc):
                return True, True
            if _is_missing_message_error(exc):
                return False, True
            logger.warning("edit_message_caption failed: %s", exc)
            return False, True
        except TelegramForbiddenError:
            return False, True
        except Exception as exc:
            logger.warning("Unexpected error editing photo card: %s", type(exc).__name__)
            return False, True

    ok = await edit_message_text_safe(
        bot,
        chat_id=chat_id,
        message_id=message_id,
        text=caption,
        reply_markup=reply_markup,
    )
    return ok, False
