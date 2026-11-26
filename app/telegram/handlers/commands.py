"""Public command handlers for Kayi Arena (/start, /arena, /game, /list, etc.)."""

from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.types import Message

from app.matches import MatchManagementErrorCode
from app.telegram.constants import LEADERBOARD_PER_PAGE
from app.telegram.keyboards import (
    build_active_game_keyboard,
    build_catalogue_universes_keyboard,
    build_help_keyboard,
    build_home_keyboard,
    build_leaderboard_keyboard,
    build_no_active_game_keyboard,
    build_universe_selection_keyboard,
)
from app.telegram.safe_api import send_message_safe, send_photo_or_text_safe
from app.telegram.service import ArenaTelegramCoordinator, UniverseMenuContext
from app.telegram.texts import (
    render_active_game,
    render_catalogue_universes,
    render_help_topic,
    render_history,
    render_home_group,
    render_home_private,
    render_leaderboard,
    render_no_active_game,
    render_profile,
    render_universe_selection,
)

# Router factory defined at bottom of module


async def cmd_start(message: Message, coordinator: ArenaTelegramCoordinator) -> None:
    coordinator.register_user(message.from_user)
    if message.chat.type == "private":
        caption = render_home_private()
        markup = build_home_keyboard(coordinator.config)
        if coordinator.config.home_banner_ref:
            await send_photo_or_text_safe(
                coordinator.bot,
                chat_id=message.chat.id,
                photo=coordinator.config.home_banner_ref,
                caption=caption,
                reply_markup=markup,
            )
            return
        await send_message_safe(
            coordinator.bot,
            chat_id=message.chat.id,
            text=caption,
            reply_markup=markup,
        )
        return

    await send_message_safe(
        coordinator.bot,
        chat_id=message.chat.id,
        text=render_home_group(),
    )


async def cmd_arena(
    message: Message,
    command: CommandObject,
    coordinator: ArenaTelegramCoordinator,
) -> None:
    player_id = coordinator.register_user(message.from_user)
    if not player_id:
        return

    target_player_id: str | None = None
    target_player_name: str | None = None
    reply = message.reply_to_message
    if reply is not None and reply.from_user is not None:
        if reply.from_user.is_bot:
            await send_message_safe(
                coordinator.bot,
                chat_id=message.chat.id,
                text="⚠️ Bots cannot participate in Kayi Arena matches.",
                reply_to_message_id=message.message_id,
            )
            return
        if str(reply.from_user.id) == player_id:
            await send_message_safe(
                coordinator.bot,
                chat_id=message.chat.id,
                text="⚠️ You cannot challenge yourself.",
                reply_to_message_id=message.message_id,
            )
            return
        target_player_id = coordinator.register_user(reply.from_user)
        target_player_name = coordinator.display_name(target_player_id)

    arg = (command.args or "").strip()
    if not arg:
        universes = coordinator.eligible_universes()
        text = render_universe_selection(
            universes=universes,
            game_mode="ranked",
            target_player_name=target_player_name,
        )
        markup = build_universe_selection_keyboard(
            universes=universes,
            page=0,
            game_mode="ranked",
        )
        sent = await send_message_safe(
            coordinator.bot,
            chat_id=message.chat.id,
            text=text,
            reply_markup=markup,
            reply_to_message_id=message.message_id,
        )
        if sent is not None and universes:
            coordinator.save_universe_menu(
                str(sent.chat.id),
                sent.message_id,
                UniverseMenuContext(
                    owner_user_id=player_id,
                    target_player_id=target_player_id,
                    target_player_name=target_player_name,
                    game_mode="ranked",
                    page=0,
                ),
            )
        return

    _, res = await coordinator.manager.handle_draft_command(
        player_id=player_id,
        chat_id=str(message.chat.id),
        universe_arg=arg,
        reply_to_user_id=target_player_id,
        game_mode="ranked",
    )
    if res is None or not res.accepted or res.challenge is None:
        err_msg = _friendly_challenge_error(res.error_code if res else None, res.message if res else "")
        await send_message_safe(
            coordinator.bot,
            chat_id=message.chat.id,
            text=f"⚠️ {err_msg}",
            reply_to_message_id=message.message_id,
        )
        return

    await coordinator.render_challenge_message(res.challenge, chat_id=str(message.chat.id))
    coordinator.schedule_challenge_expiry(res.challenge)


async def cmd_game(message: Message, coordinator: ArenaTelegramCoordinator) -> None:
    player_id = coordinator.register_user(message.from_user)
    match = coordinator.manager.get_active_match_for_player(player_id)
    if match is None:
        await send_message_safe(
            coordinator.bot,
            chat_id=message.chat.id,
            text=render_no_active_game(),
            reply_markup=build_no_active_game_keyboard(),
        )
        return

    await send_message_safe(
        coordinator.bot,
        chat_id=message.chat.id,
        text=render_active_game(
            match,
            requester_id=player_id,
            universe_name=coordinator.universe_name(match.universe_id),
            player_names=coordinator.player_names_for_match(match),
        ),
        reply_markup=build_active_game_keyboard(
            match,
            game_link=coordinator.build_game_link(match),
        ),
    )


async def cmd_list(message: Message, coordinator: ArenaTelegramCoordinator) -> None:
    coordinator.register_user(message.from_user)
    universes = coordinator.eligible_universes()
    await send_message_safe(
        coordinator.bot,
        chat_id=message.chat.id,
        text=render_catalogue_universes(universes),
        reply_markup=build_catalogue_universes_keyboard(universes),
    )


async def cmd_profile(message: Message, coordinator: ArenaTelegramCoordinator) -> None:
    player_id = coordinator.register_user(message.from_user)
    profile = await coordinator.stats_provider.get_profile(player_id)
    await send_message_safe(
        coordinator.bot,
        chat_id=message.chat.id,
        text=render_profile(profile, fallback_name=coordinator.display_name(player_id)),
    )


async def cmd_leaderboard(message: Message, coordinator: ArenaTelegramCoordinator) -> None:
    player_id = coordinator.register_user(message.from_user)
    available = coordinator.stats_provider.is_available()
    entries, pos, total_pages = await coordinator.stats_provider.get_leaderboard(
        scope="g",
        chat_id=str(message.chat.id),
        page=0,
        per_page=LEADERBOARD_PER_PAGE,
        requester_id=player_id,
    )
    await send_message_safe(
        coordinator.bot,
        chat_id=message.chat.id,
        text=render_leaderboard(entries, scope="g", requester_position=pos, available=available),
        reply_markup=build_leaderboard_keyboard(
            scope="g", page=0, total_pages=total_pages, available=available
        ),
    )


async def cmd_history(message: Message, coordinator: ArenaTelegramCoordinator) -> None:
    player_id = coordinator.register_user(message.from_user)
    available = coordinator.stats_provider.is_available()
    entries, _ = await coordinator.stats_provider.get_history(player_id, page=0, per_page=10)
    await send_message_safe(
        coordinator.bot,
        chat_id=message.chat.id,
        text=render_history(entries, available=available),
    )


async def cmd_help(message: Message, coordinator: ArenaTelegramCoordinator) -> None:
    coordinator.register_user(message.from_user)
    await send_message_safe(
        coordinator.bot,
        chat_id=message.chat.id,
        text=render_help_topic("menu"),
        reply_markup=build_help_keyboard("menu"),
    )


async def cmd_ping(message: Message, coordinator: ArenaTelegramCoordinator) -> None:
    coordinator.register_user(message.from_user)
    await send_message_safe(
        coordinator.bot,
        chat_id=message.chat.id,
        text="🏓 <b>Pong!</b> Kayi Arena is online.",
    )


def _friendly_challenge_error(code: MatchManagementErrorCode | None, default_msg: str) -> str:
    if code is MatchManagementErrorCode.PLAYER_ALREADY_IN_MATCH:
        return "You already have an active match."
    if code is MatchManagementErrorCode.NO_ELIGIBLE_UNIVERSES:
        return "No active universes with published datasets are available."
    if code is MatchManagementErrorCode.UNIVERSE_NOT_ELIGIBLE:
        return "That universe is not active or has no published dataset."
    if code is MatchManagementErrorCode.SELF_CHALLENGE_FORBIDDEN:
        return "You cannot challenge yourself."
    return default_msg or "Unable to create challenge."


def build_commands_router() -> Router:
    r = Router(name="kayi_arena_commands")
    r.message.register(cmd_start, CommandStart())
    r.message.register(cmd_arena, Command("arena"))
    r.message.register(cmd_game, Command("game"))
    r.message.register(cmd_list, Command("list"))
    r.message.register(cmd_profile, Command("profile"))
    r.message.register(cmd_leaderboard, Command("leaderboard"))
    r.message.register(cmd_history, Command("history"))
    r.message.register(cmd_help, Command("help"))
    r.message.register(cmd_ping, Command("ping"))
    return r
