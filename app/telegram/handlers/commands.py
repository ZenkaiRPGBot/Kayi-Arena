"""Public command handlers for Kayi Arena (/start, /arena, /game, /list, etc.)."""

from __future__ import annotations

import time

from aiogram import Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.types import Message

from app.matches import MatchManagementErrorCode
from app.scoring import DatasetKind
from app.telegram.constants import LEADERBOARD_PER_PAGE
from app.telegram.keyboards import (
    build_active_game_keyboard,
    build_arena_config_keyboard,
    build_arena_private_keyboard,
    build_catalogue_universes_keyboard,
    build_help_keyboard,
    build_home_keyboard,
    build_invalid_universe_keyboard,
    build_leaderboard_keyboard,
    build_no_active_game_keyboard,
    build_profile_keyboard,
    build_universe_browser_keyboard,
    build_universe_selection_keyboard,
)
from app.telegram.safe_api import (
    send_message_safe,
    send_photo_or_text_safe,
    send_video_or_text_safe,
)
from app.telegram.service import ArenaTelegramCoordinator, UniverseMenuContext
from app.telegram.texts import (
    render_active_game,
    render_arena_config,
    render_arena_private,
    render_catalogue_universes,
    render_help_topic,
    render_history,
    render_home_group,
    render_home_private,
    render_invalid_universe,
    render_leaderboard,
    render_no_active_game,
    render_profile,
    render_universe_browser,
    render_universe_selection,
)

# Router factory defined at bottom of module


async def cmd_start(message: Message, coordinator: ArenaTelegramCoordinator) -> None:
    coordinator.register_user(message.from_user)
    if message.chat.type == "private":
        caption = render_home_private()
        markup = build_home_keyboard(coordinator.config)
        welcome_video = coordinator.get_welcome_video_file_id()
        if welcome_video:
            sent, is_video = await send_video_or_text_safe(
                coordinator.bot,
                chat_id=message.chat.id,
                video=welcome_video,
                caption=caption,
                reply_markup=markup,
            )
            if is_video and sent is not None and getattr(sent, "video", None):
                vid_id = getattr(sent.video, "file_id", "")
                if vid_id and vid_id != welcome_video:
                    coordinator.set_welcome_video_file_id(vid_id)
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
    if message.chat.type not in {"group", "supergroup"}:
        await send_message_safe(
            coordinator.bot,
            chat_id=message.chat.id,
            text=render_arena_private(),
            reply_markup=build_arena_private_keyboard(coordinator.config),
        )
        return
    if (
        coordinator.config.dataset_kind is DatasetKind.TEST
        and not coordinator.config.is_authorized_tester(player_id)
    ):
        await send_message_safe(
            coordinator.bot,
            chat_id=message.chat.id,
            text="🔒 Testing dataset access is restricted to authorized testers.",
            reply_to_message_id=message.message_id,
        )
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

    universes = coordinator.eligible_universes()
    arg = (command.args or "").strip()

    if not arg:
        if not universes:
            await send_message_safe(
                coordinator.bot,
                chat_id=message.chat.id,
                text=render_universe_browser(has_universes=False),
                reply_to_message_id=message.message_id,
            )
            return
        ctx = UniverseMenuContext(
            owner_user_id=player_id,
            chat_id=str(message.chat.id),
            target_player_id=target_player_id,
            target_player_name=target_player_name,
            selected_universe_id=None,
            explicit_universe_mode=False,
            game_mode="ranked",
            page=0,
            screen="config",
            created_at=time.time(),
        )
        sent = await send_message_safe(
            coordinator.bot,
            chat_id=message.chat.id,
            text=render_arena_config(
                selected_universe_id=None,
                universe_name=None,
                game_mode="ranked",
            ),
            reply_markup=build_arena_config_keyboard(
                selected_universe_id=None,
                game_mode="ranked",
                explicit_universe_mode=False,
            ),
            reply_to_message_id=message.message_id,
        )
        if sent is not None:
            coordinator.save_universe_menu(str(sent.chat.id), sent.message_id, ctx)
        return

    if arg.lower() == "random":
        if not universes:
            await send_message_safe(
                coordinator.bot,
                chat_id=message.chat.id,
                text=render_universe_browser(has_universes=False),
                reply_to_message_id=message.message_id,
            )
            return
        ctx = UniverseMenuContext(
            owner_user_id=player_id,
            chat_id=str(message.chat.id),
            target_player_id=target_player_id,
            target_player_name=target_player_name,
            selected_universe_id="random",
            explicit_universe_mode=True,
            game_mode="ranked",
            page=0,
            screen="config",
            created_at=time.time(),
        )
        sent = await send_message_safe(
            coordinator.bot,
            chat_id=message.chat.id,
            text=render_arena_config(
                selected_universe_id="random",
                universe_name="Random",
                game_mode="ranked",
            ),
            reply_markup=build_arena_config_keyboard(
                selected_universe_id="random",
                game_mode="ranked",
                explicit_universe_mode=True,
            ),
            reply_to_message_id=message.message_id,
        )
        if sent is not None:
            coordinator.save_universe_menu(str(sent.chat.id), sent.message_id, ctx)
        return

    resolved = coordinator.manager._resolve_universe_id(arg)
    if resolved is None:
        has_any = bool(universes)
        ctx = UniverseMenuContext(
            owner_user_id=player_id,
            chat_id=str(message.chat.id),
            target_player_id=target_player_id,
            target_player_name=target_player_name,
            selected_universe_id=None,
            explicit_universe_mode=False,
            game_mode="ranked",
            page=0,
            screen="invalid",
            invalid_universe_arg=arg,
            created_at=time.time(),
        )
        sent = await send_message_safe(
            coordinator.bot,
            chat_id=message.chat.id,
            text=render_invalid_universe(arg, has_eligible_universes=has_any),
            reply_markup=build_invalid_universe_keyboard(has_eligible_universes=has_any),
            reply_to_message_id=message.message_id,
        )
        if sent is not None:
            coordinator.save_universe_menu(str(sent.chat.id), sent.message_id, ctx)
        return

    ctx = UniverseMenuContext(
        owner_user_id=player_id,
        chat_id=str(message.chat.id),
        target_player_id=target_player_id,
        target_player_name=target_player_name,
        selected_universe_id=resolved,
        explicit_universe_mode=True,
        game_mode="ranked",
        page=0,
        screen="config",
        created_at=time.time(),
    )
    sent = await send_message_safe(
        coordinator.bot,
        chat_id=message.chat.id,
        text=render_arena_config(
            selected_universe_id=resolved,
            universe_name=coordinator.universe_name(resolved),
            game_mode="ranked",
        ),
        reply_markup=build_arena_config_keyboard(
            selected_universe_id=resolved,
            game_mode="ranked",
            explicit_universe_mode=True,
        ),
        reply_to_message_id=message.message_id,
    )
    if sent is not None:
        coordinator.save_universe_menu(str(sent.chat.id), sent.message_id, ctx)


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
    player_id = coordinator.register_user(message.from_user)
    if (
        coordinator.config.dataset_kind is DatasetKind.TEST
        and not coordinator.config.is_authorized_tester(player_id)
    ):
        await send_message_safe(
            coordinator.bot,
            chat_id=message.chat.id,
            text="🔒 Testing dataset catalogue is restricted to authorized testers.",
        )
        return
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
        reply_markup=build_profile_keyboard(player_id),
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
    from app.telegram.constants import MAX_CAPTION_LENGTH

    player_id = coordinator.register_user(message.from_user)
    text = render_help_topic("menu")
    markup = build_help_keyboard("menu")
    photo_id = coordinator.get_handbook_illustration_file_id("menu")
    if photo_id and len(text) <= MAX_CAPTION_LENGTH:
        sent, _ = await send_photo_or_text_safe(
            coordinator.bot,
            chat_id=message.chat.id,
            photo=photo_id,
            caption=text,
            reply_markup=markup,
        )
    else:
        sent = await send_message_safe(
            coordinator.bot,
            chat_id=message.chat.id,
            text=text,
            reply_markup=markup,
        )
    if sent is not None and player_id:
        coordinator.register_handbook_message(message.chat.id, sent.message_id, player_id)


async def cmd_ping(message: Message, coordinator: ArenaTelegramCoordinator) -> None:
    app_t0 = time.perf_counter()
    coordinator.register_user(message.from_user)

    db_t0 = time.perf_counter()
    db_ok, db_msg = (
        coordinator.store.integrity_check()
        if coordinator.store is not None
        else (True, "in-memory")
    )
    db_ms = (time.perf_counter() - db_t0) * 1000.0

    tg_ms: float | None = None
    if hasattr(coordinator.bot, "get_me"):
        tg_t0 = time.perf_counter()
        try:
            await coordinator.bot.get_me()
            tg_ms = (time.perf_counter() - tg_t0) * 1000.0
        except Exception:
            tg_ms = None

    app_ms = max(0.0, (time.perf_counter() - app_t0) * 1000.0 - db_ms - (tg_ms or 0.0))
    tg_str = f"{tg_ms:.1f} ms" if tg_ms is not None else "N/A"
    lines = [
        "🏓 <b>Pong!</b> Kayi Arena is online.",
        "",
        f"• App processing: <code>{app_ms:.2f} ms</code>",
        f"• Database ({'OK' if db_ok else 'ERR'}): <code>{db_ms:.2f} ms</code>",
        f"• Telegram API (getMe): <code>{tg_str}</code>",
    ]
    pct = coordinator.latency_percentiles()
    if pct is not None:
        lines.append(
            f"• Rolling ({int(pct['count'])} reqs): "
            f"P50 <code>{pct['median']:.1f}ms</code> | "
            f"P95 <code>{pct['p95']:.1f}ms</code> | "
            f"P99 <code>{pct['p99']:.1f}ms</code>"
        )
    await send_message_safe(
        coordinator.bot,
        chat_id=message.chat.id,
        text="\n".join(lines),
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
