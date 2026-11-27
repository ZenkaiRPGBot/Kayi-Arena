"""Callback query handlers for Kayi Arena with strict authorization & generation checks."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.types import CallbackQuery

from app.engine import ErrorCode as DraftErrorCode
from app.matches import MatchLifecycleStatus, MatchManagementErrorCode, MessageReference
from app.telegram.callbacks import code_to_rarity, decode_cb, index_to_role
from app.telegram.constants import CATALOGUE_PER_PAGE, LEADERBOARD_PER_PAGE
from app.telegram.keyboards import (
    build_active_game_keyboard,
    build_arena_config_keyboard,
    build_arena_private_keyboard,
    build_catalogue_page_keyboard,
    build_catalogue_universes_keyboard,
    build_forfeit_confirm_keyboard,
    build_help_keyboard,
    build_history_keyboard,
    build_home_keyboard,
    build_leaderboard_keyboard,
    build_match_results_keyboard,
    build_profile_keyboard,
    build_recover_confirm_keyboard,
    build_recover_success_keyboard,
    build_support_keyboard,
    build_universe_browser_keyboard,
    build_universe_selection_keyboard,
)
from app.telegram.safe_api import (
    answer_callback_safe,
    edit_card_message_safe,
    edit_message_text_safe,
    replace_text_with_photo_card_safe,
    send_message_safe,
    send_video_or_text_safe,
)
from app.telegram.service import ArenaTelegramCoordinator, UniverseMenuContext
from app.telegram.texts import (
    render_active_game,
    render_arena_config,
    render_arena_private,
    render_catalogue_page,
    render_catalogue_universes,
    render_forfeit_confirmation,
    render_help_topic,
    render_history,
    render_home_group,
    render_home_private,
    render_leaderboard,
    render_match_results,
    render_profile,
    render_recover_confirmation,
    render_recover_failed,
    render_recover_success,
    render_support_home,
    render_universe_browser,
    render_universe_selection,
)

# Router factory defined at bottom of module


def _parse_int(value: str) -> int | None:
    try:
        return int(value)
    except ValueError:
        return None


def _map_match_error(code: MatchManagementErrorCode | None, draft_code: DraftErrorCode | None) -> str:
    if code is MatchManagementErrorCode.NOT_MATCH_PARTICIPANT:
        return "You are not a participant in this match."
    if code is MatchManagementErrorCode.STALE_CONTROL_GENERATION or draft_code is DraftErrorCode.STALE_REVISION:
        return "This gameplay interface is outdated.\nUse /game to access the latest match messages."
    if code is MatchManagementErrorCode.MATCH_NOT_ACTIVE:
        return "This match has already ended."
    if code is MatchManagementErrorCode.SELF_EXTENSION_FORBIDDEN:
        return "Only your opponent may grant a turn extension."
    if code is MatchManagementErrorCode.NO_EXTENSIONS_REMAINING:
        return "No extensions remaining for this player."
    if code is MatchManagementErrorCode.NO_INACTIVITY_CLAIM_PENDING:
        return "Inactivity claim is not available."
    if draft_code is DraftErrorCode.NOT_YOUR_TURN:
        return "It's not your turn."
    if draft_code is DraftErrorCode.ROLE_OCCUPIED:
        return "That role has already been assigned."
    if draft_code is DraftErrorCode.NO_SKIPS_REMAINING:
        return "No skips remaining."
    if draft_code is DraftErrorCode.WRONG_PHASE:
        return "That action is not available right now."
    return "Action could not be completed."


def _map_challenge_error(
    code: MatchManagementErrorCode | None,
    *,
    action: str | None = None,
) -> str:
    if code is MatchManagementErrorCode.SELF_CHALLENGE_FORBIDDEN:
        return "You cannot accept your own challenge."
    if code is MatchManagementErrorCode.NOT_CHALLENGE_TARGET:
        if action == "cd":
            return "Only the challenged player can decline."
        return "Only the challenged player can accept."
    if code is MatchManagementErrorCode.NOT_CHALLENGER:
        return "Only the challenger can cancel."
    if code is MatchManagementErrorCode.PLAYER_ALREADY_IN_MATCH:
        return "You already have an active match."
    if code in {
        MatchManagementErrorCode.CHALLENGE_EXPIRED,
        MatchManagementErrorCode.CHALLENGE_NOT_OPEN,
        MatchManagementErrorCode.STALE_CONTROL_GENERATION,
        MatchManagementErrorCode.CHALLENGE_NOT_FOUND,
    }:
        return "This challenge has already ended."
    return "Unable to update challenge."


async def handle_arena_callback(
    query: CallbackQuery,
    coordinator: ArenaTelegramCoordinator,
) -> None:
    parsed = decode_cb(query.data)
    if parsed is None:
        await answer_callback_safe(query, "Invalid action.", show_alert=True)
        return

    user_id = coordinator.register_user(query.from_user)
    msg = query.message
    if msg is None:
        await answer_callback_safe(query, "Message is no longer available.", show_alert=True)
        return
    chat_id = str(msg.chat.id)
    msg_id = msg.message_id
    action = parsed.action
    args = parsed.args

    if action == "noop":
        await answer_callback_safe(query)
        return

    # ------------------------------------------------------------------
    # Navigation: Home, Help, Profile, Leaderboard, Catalogue
    # ------------------------------------------------------------------
    if action == "home":
        if msg.chat.type == "private":
            caption = render_home_private()
            markup = build_home_keyboard(coordinator.config)
            welcome_video = coordinator.get_welcome_video_file_id()
            if welcome_video:
                sent, is_video = await send_video_or_text_safe(
                    coordinator.bot,
                    chat_id=chat_id,
                    video=welcome_video,
                    caption=caption,
                    reply_markup=markup,
                )
                if is_video and sent is not None and getattr(sent, "video", None):
                    vid_id = getattr(sent.video, "file_id", "")
                    if vid_id and vid_id != welcome_video:
                        coordinator.set_welcome_video_file_id(vid_id)
                if sent is not None:
                    try:
                        await coordinator.bot.delete_message(chat_id=chat_id, message_id=msg_id)
                    except Exception:
                        pass
            elif getattr(msg, "text", None) is None:
                sent = await send_message_safe(
                    coordinator.bot,
                    chat_id=chat_id,
                    text=caption,
                    reply_markup=markup,
                )
                if sent is not None:
                    try:
                        await coordinator.bot.delete_message(chat_id=chat_id, message_id=msg_id)
                    except Exception:
                        pass
            else:
                await edit_message_text_safe(
                    coordinator.bot,
                    chat_id=chat_id,
                    message_id=msg_id,
                    text=caption,
                    reply_markup=markup,
                )
        else:
            await edit_message_text_safe(
                coordinator.bot,
                chat_id=chat_id,
                message_id=msg_id,
                text=render_home_group(),
            )
        await answer_callback_safe(query)
        return

    if action == "sup":
        if msg.chat.type != "private":
            await answer_callback_safe(query, "Support is available in private chat.", show_alert=True)
            return
        sub = args[0] if args else "menu"
        if sub == "bug":
            await answer_callback_safe(query, "Bug reporting is not available yet.", show_alert=True)
            return
        if sub == "idea":
            await answer_callback_safe(query, "Feature suggestions are not available yet.", show_alert=True)
            return
        if sub == "menu":
            support_text = render_support_home()
            support_markup = build_support_keyboard()
            if getattr(msg, "text", None) is None:
                sent = await send_message_safe(
                    coordinator.bot,
                    chat_id=chat_id,
                    text=support_text,
                    reply_markup=support_markup,
                )
                if sent is not None:
                    try:
                        await coordinator.bot.delete_message(chat_id=chat_id, message_id=msg_id)
                    except Exception:
                        pass
            else:
                await edit_message_text_safe(
                    coordinator.bot,
                    chat_id=chat_id,
                    message_id=msg_id,
                    text=support_text,
                    reply_markup=support_markup,
                )
            await answer_callback_safe(query)
            return
        await answer_callback_safe(query, "This action is no longer available.")
        return

    if action == "hlp":
        from app.telegram.constants import MAX_CAPTION_LENGTH

        if msg.chat.type != "private":
            owner_id = coordinator.get_handbook_owner(chat_id, msg_id)
            if owner_id is not None and owner_id != user_id:
                await answer_callback_safe(
                    query,
                    "Only the player who opened this handbook can navigate it.",
                    show_alert=True,
                )
                return

        topic = args[0] if args else "menu"
        if topic not in {"menu", "1", "2", "3", "4", "5", "6"}:
            topic = "menu"
        text = render_help_topic(topic)
        markup = build_help_keyboard(topic)
        photo_id = coordinator.get_handbook_illustration_file_id(topic)
        use_photo = bool(photo_id and len(text) <= MAX_CAPTION_LENGTH)
        currently_media = getattr(msg, "text", None) is None

        if currently_media:
            if use_photo:
                await edit_card_message_safe(
                    coordinator.bot,
                    chat_id=chat_id,
                    message_id=msg_id,
                    is_photo=True,
                    photo=photo_id,
                    caption=text,
                    reply_markup=markup,
                )
            else:
                sent = await send_message_safe(
                    coordinator.bot,
                    chat_id=chat_id,
                    text=text,
                    reply_markup=markup,
                )
                if sent is not None:
                    coordinator.register_handbook_message(chat_id, sent.message_id, user_id)
                    try:
                        await coordinator.bot.delete_message(chat_id=chat_id, message_id=msg_id)
                    except Exception:
                        pass
        else:
            if use_photo:
                sent, _ = await replace_text_with_photo_card_safe(
                    coordinator.bot,
                    chat_id=chat_id,
                    old_message_id=msg_id,
                    photo=photo_id,
                    caption=text,
                    reply_markup=markup,
                )
                if sent is not None:
                    coordinator.register_handbook_message(chat_id, sent.message_id, user_id)
            else:
                await edit_message_text_safe(
                    coordinator.bot,
                    chat_id=chat_id,
                    message_id=msg_id,
                    text=text,
                    reply_markup=markup,
                )
        await answer_callback_safe(query)
        return

    if action == "pr":
        target_id = user_id if (not args or args[0] == "self") else args[0]
        profile = await coordinator.stats_provider.get_profile(target_id)
        text = render_profile(profile, fallback_name=coordinator.display_name(target_id))
        markup = build_profile_keyboard(target_id)
        if getattr(msg, "text", None) and "Match History" in msg.text:
            await edit_message_text_safe(
                coordinator.bot,
                chat_id=chat_id,
                message_id=msg_id,
                text=text,
                reply_markup=markup,
            )
        else:
            await send_message_safe(
                coordinator.bot,
                chat_id=chat_id,
                text=text,
                reply_markup=markup,
            )
        await answer_callback_safe(query)
        return

    if action == "hs":
        target_id = args[0] if args else user_id
        page = _parse_int(args[1]) if len(args) >= 2 else 0
        safe_page = max(0, page or 0)
        available = coordinator.stats_provider.is_available()
        entries, total_pages = await coordinator.stats_provider.get_history(
            target_id, page=safe_page, per_page=10
        )
        await edit_message_text_safe(
            coordinator.bot,
            chat_id=chat_id,
            message_id=msg_id,
            text=render_history(entries, available=available),
            reply_markup=build_history_keyboard(
                target_id=target_id, page=safe_page, total_pages=total_pages
            ),
        )
        await answer_callback_safe(query)
        return

    if action == "lb":
        scope = args[0] if len(args) >= 1 and args[0] in {"g", "c"} else "g"
        page = _parse_int(args[1]) if len(args) >= 2 else 0
        safe_page = max(0, page or 0)
        available = coordinator.stats_provider.is_available()
        entries, pos, total_pages = await coordinator.stats_provider.get_leaderboard(
            scope=scope,
            chat_id=chat_id,
            page=safe_page,
            per_page=LEADERBOARD_PER_PAGE,
            requester_id=user_id,
        )
        await edit_message_text_safe(
            coordinator.bot,
            chat_id=chat_id,
            message_id=msg_id,
            text=render_leaderboard(entries, scope=scope, requester_position=pos, available=available),
            reply_markup=build_leaderboard_keyboard(
                scope=scope, page=safe_page, total_pages=total_pages, available=available
            ),
        )
        await answer_callback_safe(query)
        return

    if action == "ls":
        target = args[0] if len(args) >= 1 else "menu"
        rarity_filter = code_to_rarity(args[1]) if len(args) >= 2 else "all"
        page = max(0, (_parse_int(args[2]) if len(args) >= 3 else 0) or 0)
        universes = coordinator.eligible_universes()
        if target == "menu":
            await edit_message_text_safe(
                coordinator.bot,
                chat_id=chat_id,
                message_id=msg_id,
                text=render_catalogue_universes(universes),
                reply_markup=build_catalogue_universes_keyboard(universes),
            )
            await answer_callback_safe(query)
            return

        universe = next((u for u in universes if u.universe_id == target), None)
        if universe is None:
            await answer_callback_safe(query, "Universe is not available.", show_alert=True)
            return
        dver = coordinator.db.get_latest_published_version(
            universe.universe_id, kind=coordinator.config.dataset_kind
        )
        if dver is None:
            await answer_callback_safe(query, "No published dataset available.", show_alert=True)
            return
        manifest = coordinator.db.load_manifest(dver)
        chars = []
        for rec in manifest.records:
            entry = coordinator.get_character_entry(rec.character_id)
            if entry is not None and (rarity_filter == "all" or entry.rarity == rarity_filter):
                chars.append(entry)
        chars.sort(key=lambda r: (r.name.lower(), r.character_id))
        total_pages = max(1, (len(chars) + CATALOGUE_PER_PAGE - 1) // CATALOGUE_PER_PAGE)
        safe_page = min(page, total_pages - 1)
        chunk = chars[safe_page * CATALOGUE_PER_PAGE : (safe_page + 1) * CATALOGUE_PER_PAGE]
        await edit_message_text_safe(
            coordinator.bot,
            chat_id=chat_id,
            message_id=msg_id,
            text=render_catalogue_page(
                universe=universe,
                rarity_filter=rarity_filter,
                characters=chunk,
                page=safe_page,
                total_pages=total_pages,
            ),
            reply_markup=build_catalogue_page_keyboard(
                universe_id=universe.universe_id,
                rarity_filter=rarity_filter,
                page=safe_page,
                total_pages=total_pages,
            ),
        )
        await answer_callback_safe(query)
        return

    # ------------------------------------------------------------------
    # Arena Battle Configuration & Universe Browser (Module 04)
    # ------------------------------------------------------------------
    if action == "ac":
        import time as _time

        if msg.chat.type not in {"group", "supergroup"}:
            await answer_callback_safe(query, "Battles can only be played in groups.", show_alert=True)
            return

        ctx = coordinator.get_universe_menu(chat_id, msg_id)
        if ctx is None:
            await answer_callback_safe(query, "This configuration session has expired.", show_alert=True)
            return
        if ctx.owner_user_id != user_id:
            await answer_callback_safe(query, "Only the player who opened this configuration can use it.", show_alert=True)
            return
        if ctx.chat_id and str(ctx.chat_id) != str(chat_id):
            await answer_callback_safe(query, "This configuration is not valid in this chat.", show_alert=True)
            return
        if ctx.cancelled or ctx.confirmed:
            await answer_callback_safe(query, "This configuration session is already closed.", show_alert=True)
            return
        if ctx.created_at and (_time.time() - ctx.created_at) > 900.0:
            ctx.cancelled = True
            await answer_callback_safe(query, "This configuration session has expired.", show_alert=True)
            return

        sub = args[0] if args else ""

        if sub == "cx":
            ctx.cancelled = True
            try:
                await coordinator.bot.delete_message(chat_id=chat_id, message_id=msg_id)
            except Exception:
                await edit_message_text_safe(
                    coordinator.bot,
                    chat_id=chat_id,
                    message_id=msg_id,
                    text="Arena selection cancelled.",
                    reply_markup=None,
                )
            await answer_callback_safe(query)
            return

        if sub == "md":
            ctx.game_mode = "friendly" if (len(args) >= 2 and args[1] == "f") else "ranked"
            u_name = (
                coordinator.universe_name(ctx.selected_universe_id)
                if ctx.selected_universe_id
                else None
            )
            await edit_message_text_safe(
                coordinator.bot,
                chat_id=chat_id,
                message_id=msg_id,
                text=render_arena_config(
                    selected_universe_id=ctx.selected_universe_id,
                    universe_name=u_name,
                    game_mode=ctx.game_mode,
                ),
                reply_markup=build_arena_config_keyboard(
                    selected_universe_id=ctx.selected_universe_id,
                    game_mode=ctx.game_mode,
                    explicit_universe_mode=ctx.explicit_universe_mode,
                ),
            )
            await answer_callback_safe(query)
            return

        if sub in {"br", "bp"}:
            universes = coordinator.eligible_universes()
            if sub == "bp" and len(args) >= 2:
                ctx.page = max(0, _parse_int(args[1]) or 0)
            ctx.screen = "browser"
            await edit_message_text_safe(
                coordinator.bot,
                chat_id=chat_id,
                message_id=msg_id,
                text=render_universe_browser(has_universes=bool(universes)),
                reply_markup=build_universe_browser_keyboard(
                    universes=universes,
                    page=ctx.page,
                    selected_universe_id=ctx.selected_universe_id,
                ),
            )
            await answer_callback_safe(query)
            return

        if sub == "us":
            uid = args[1] if len(args) >= 2 else ""
            universes = coordinator.eligible_universes()
            if not any(u.universe_id == uid for u in universes):
                await answer_callback_safe(query, "That universe is no longer available.", show_alert=True)
                return
            ctx.selected_universe_id = uid
            ctx.explicit_universe_mode = False
            ctx.screen = "config"
            await edit_message_text_safe(
                coordinator.bot,
                chat_id=chat_id,
                message_id=msg_id,
                text=render_arena_config(
                    selected_universe_id=uid,
                    universe_name=coordinator.universe_name(uid),
                    game_mode=ctx.game_mode,
                ),
                reply_markup=build_arena_config_keyboard(
                    selected_universe_id=uid,
                    game_mode=ctx.game_mode,
                    explicit_universe_mode=False,
                ),
            )
            await answer_callback_safe(query)
            return

        if sub == "rn":
            if not coordinator.eligible_universes():
                await answer_callback_safe(query, "No playable universes are available.", show_alert=True)
                return
            ctx.selected_universe_id = "random"
            ctx.explicit_universe_mode = False
            ctx.screen = "config"
            await edit_message_text_safe(
                coordinator.bot,
                chat_id=chat_id,
                message_id=msg_id,
                text=render_arena_config(
                    selected_universe_id="random",
                    universe_name="Random",
                    game_mode=ctx.game_mode,
                ),
                reply_markup=build_arena_config_keyboard(
                    selected_universe_id="random",
                    game_mode=ctx.game_mode,
                    explicit_universe_mode=False,
                ),
            )
            await answer_callback_safe(query)
            return

        if sub == "bk":
            ctx.screen = "config"
            u_name = (
                coordinator.universe_name(ctx.selected_universe_id)
                if ctx.selected_universe_id
                else None
            )
            await edit_message_text_safe(
                coordinator.bot,
                chat_id=chat_id,
                message_id=msg_id,
                text=render_arena_config(
                    selected_universe_id=ctx.selected_universe_id,
                    universe_name=u_name,
                    game_mode=ctx.game_mode,
                ),
                reply_markup=build_arena_config_keyboard(
                    selected_universe_id=ctx.selected_universe_id,
                    game_mode=ctx.game_mode,
                    explicit_universe_mode=ctx.explicit_universe_mode,
                ),
            )
            await answer_callback_safe(query)
            return

        if sub == "go":
            if not ctx.selected_universe_id:
                await answer_callback_safe(query, "Please select a universe first.", show_alert=True)
                return
            ctx.confirmed = True
            try:
                res = await coordinator.manager.create_challenge(
                    challenger_id=user_id,
                    chat_id=chat_id,
                    universe_id=ctx.selected_universe_id,
                    target_player_id=ctx.target_player_id,
                    game_mode=ctx.game_mode,
                )
            except Exception:
                ctx.confirmed = False
                raise
            if not res.accepted or res.challenge is None:
                ctx.confirmed = False
                await answer_callback_safe(
                    query,
                    _map_challenge_error(res.error_code),
                    show_alert=True,
                )
                return
            sent_chl = await coordinator.render_challenge_message(res.challenge, chat_id=chat_id)
            if sent_chl is None:
                await coordinator.manager.cancel_challenge(
                    challenge_id=res.challenge.challenge_id,
                    player_id=user_id,
                    expected_generation=res.challenge.generation,
                )
                ctx.confirmed = False
                await answer_callback_safe(
                    query,
                    "Could not publish challenge message. Please try again.",
                    show_alert=True,
                )
                return
            coordinator.schedule_challenge_expiry(res.challenge)
            try:
                await coordinator.bot.delete_message(chat_id=chat_id, message_id=msg_id)
            except Exception:
                await edit_message_text_safe(
                    coordinator.bot,
                    chat_id=chat_id,
                    message_id=msg_id,
                    text=f"⚔️ Challenge created in <b>{coordinator.universe_name(res.challenge.universe_id)}</b>.",
                    reply_markup=None,
                )
            await answer_callback_safe(query)
            return

        await answer_callback_safe(query, "This action is no longer available.")
        return

    if action == "arena":
        if msg.chat.type not in {"group", "supergroup"}:
            await answer_callback_safe(query, "Battles can only be played in groups.", show_alert=True)
            return
        universes = coordinator.eligible_universes()
        coordinator.save_universe_menu(
            chat_id,
            msg_id,
            UniverseMenuContext(
                owner_user_id=user_id,
                chat_id=chat_id,
                game_mode="ranked",
                page=0,
            ),
        )
        await edit_message_text_safe(
            coordinator.bot,
            chat_id=chat_id,
            message_id=msg_id,
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
        )
        await answer_callback_safe(query)
        return

    if action in {"um", "u"}:
        if msg.chat.type not in {"group", "supergroup"}:
            await answer_callback_safe(query, "Battles can only be played in groups.", show_alert=True)
            return
        ctx = coordinator.get_universe_menu(chat_id, msg_id)
        if ctx is not None and ctx.owner_user_id != user_id:
            await answer_callback_safe(query, "Only the command sender can use this menu.", show_alert=True)
            return
        if ctx is None:
            ctx = UniverseMenuContext(owner_user_id=user_id)
            coordinator.save_universe_menu(chat_id, msg_id, ctx)

        page = max(0, (_parse_int(args[0]) if len(args) >= 1 else 0) or 0)
        mode = "friendly" if (len(args) >= 2 and args[1] == "f") else "ranked"
        ctx.page = page
        ctx.game_mode = mode

        if action == "um":
            universes = coordinator.eligible_universes()
            await edit_message_text_safe(
                coordinator.bot,
                chat_id=chat_id,
                message_id=msg_id,
                text=render_universe_selection(
                    universes=universes,
                    game_mode=mode,
                    target_player_name=ctx.target_player_name,
                ),
                reply_markup=build_universe_selection_keyboard(
                    universes=universes, page=page, game_mode=mode
                ),
            )
            await answer_callback_safe(query)
            return

        uid_arg = args[2] if len(args) >= 3 else ""
        universe_arg = "random" if uid_arg == "rand" else uid_arg
        _, res = await coordinator.manager.handle_draft_command(
            player_id=user_id,
            chat_id=chat_id,
            universe_arg=universe_arg,
            reply_to_user_id=ctx.target_player_id,
            game_mode=mode,
        )
        if res is None or not res.accepted or res.challenge is None:
            await answer_callback_safe(
                query,
                _map_challenge_error(res.error_code if res else None),
                show_alert=True,
            )
            return
        await edit_message_text_safe(
            coordinator.bot,
            chat_id=chat_id,
            message_id=msg_id,
            text=f"⚔️ Challenge created in <b>{coordinator.universe_name(res.challenge.universe_id)}</b>.",
            reply_markup=None,
        )
        await coordinator.render_challenge_message(res.challenge, chat_id=chat_id)
        coordinator.schedule_challenge_expiry(res.challenge)
        await answer_callback_safe(query)
        return

    # ------------------------------------------------------------------
    # Challenge Actions: Accept, Decline, Cancel (and obsolete Mode Switch)
    # ------------------------------------------------------------------
    if action in {"ca", "cd", "cm", "cx"}:
        if msg.chat.type not in {"group", "supergroup"}:
            await answer_callback_safe(query, "Battles can only be played in groups.", show_alert=True)
            return
        if len(args) < 2:
            await answer_callback_safe(query, "Invalid challenge action.", show_alert=True)
            return
        challenge_id = args[0]
        gen = _parse_int(args[1])
        if gen is None:
            await answer_callback_safe(query, "Invalid challenge state.", show_alert=True)
            return

        if action == "cm":
            await answer_callback_safe(
                query,
                "Match mode cannot be changed after sending a challenge.",
                show_alert=True,
            )
            return

        if action == "ca":
            res = await coordinator.manager.accept_challenge(
                challenge_id=challenge_id,
                player_id=user_id,
                expected_generation=gen,
            )
            if not res.accepted or res.challenge is None or res.match is None:
                await answer_callback_safe(
                    query,
                    _map_challenge_error(res.error_code, action="ca"),
                    show_alert=True,
                )
                return
            coordinator.cancel_challenge_expiry(challenge_id)
            ui_state = None
            try:
                ui_state = await coordinator.start_match_ui(
                    res.match,
                    chat_id=chat_id,
                    reuse_challenge_message_id=msg_id,
                )
            except Exception as exc:
                import logging

                logging.getLogger(__name__).warning(
                    "Post-commit start_match_ui error on %s: %s",
                    res.match.match_id,
                    type(exc).__name__,
                )
            if ui_state is None:
                coordinator.schedule_turn_timeout(res.match)
                await answer_callback_safe(
                    query,
                    "Match started! Use /game if the board did not appear.",
                    show_alert=True,
                )
                return
            await answer_callback_safe(query, "Challenge accepted!")
            return

        if action == "cd":
            res = await coordinator.manager.decline_challenge(
                challenge_id=challenge_id,
                player_id=user_id,
                expected_generation=gen,
            )
            if not res.accepted or res.challenge is None:
                await answer_callback_safe(
                    query,
                    _map_challenge_error(res.error_code, action="cd"),
                    show_alert=True,
                )
                return
            coordinator.cancel_challenge_expiry(challenge_id)
            await coordinator.render_challenge_message(
                res.challenge, chat_id=chat_id, message_id=msg_id
            )
            await answer_callback_safe(query, "Challenge declined.")
            return

        if action == "cx":
            res = await coordinator.manager.cancel_challenge(
                challenge_id=challenge_id,
                player_id=user_id,
                expected_generation=gen,
            )
            if not res.accepted or res.challenge is None:
                await answer_callback_safe(
                    query,
                    _map_challenge_error(res.error_code, action="cx"),
                    show_alert=True,
                )
                return
            coordinator.cancel_challenge_expiry(challenge_id)
            await coordinator.render_challenge_message(
                res.challenge, chat_id=chat_id, message_id=msg_id
            )
            await answer_callback_safe(query, "Challenge cancelled.")
            return

    # ------------------------------------------------------------------
    # Active Match Actions: Shuffle, Skip, Assign, Inactivity, Forfeit, Recover
    # ------------------------------------------------------------------
    if action == "mi":
        match_id = args[0] if args else ""
        match = coordinator.manager.get_match(match_id)
        if match is None:
            await answer_callback_safe(query, "Match not found.", show_alert=True)
            return
        p1, p2 = match.players
        info = (
            f"Match #{match.match_id}\n"
            f"Universe: {coordinator.universe_name(match.universe_id)}\n"
            f"Mode: {match.game_mode.title()}\n"
            f"Players: {coordinator.display_name(p1)} vs {coordinator.display_name(p2)}"
        )
        await answer_callback_safe(query, info[:200], show_alert=True)
        return

    if action in {"sh", "sk", "as", "cv", "ex"}:
        if len(args) < 2:
            await answer_callback_safe(query, "Invalid match action.", show_alert=True)
            return
        match_id = args[0]
        gen = _parse_int(args[1])
        if gen is None:
            await answer_callback_safe(query, "Invalid match state.", show_alert=True)
            return

        current = coordinator.manager.get_match(match_id)
        if current is None:
            await answer_callback_safe(query, "This match has already ended.", show_alert=True)
            return
        if current.status is not MatchLifecycleStatus.DRAFTING:
            await answer_callback_safe(query, "This match has already ended.", show_alert=True)
            return
        if user_id not in current.players:
            await answer_callback_safe(query, "You are not a participant in this match.", show_alert=True)
            return
        match_chat = coordinator.match_chat_id(current)
        if match_chat is not None and chat_id != match_chat:
            await answer_callback_safe(
                query,
                "This gameplay interface is outdated.\nUse /game to access the latest match messages.",
                show_alert=True,
            )
            return
        current_ui = coordinator._match_ui.get(match_id)
        if current_ui is not None and msg_id != current_ui.card_message_id:
            await answer_callback_safe(
                query,
                "This gameplay interface is outdated.\nUse /game to access the latest match messages.",
                show_alert=True,
            )
            return

        if action == "sh":
            res = await coordinator.manager.shuffle_match(
                match_id=match_id,
                player_id=user_id,
                expected_revision=current.draft_snapshot.revision,
                expected_generation=gen,
            )
            if not res.accepted or res.match is None:
                await answer_callback_safe(
                    query, _map_match_error(res.error_code, res.draft_error_code), show_alert=True
                )
                return
            await coordinator.sync_match_ui(
                res.match,
                update_board=True,
                update_card=True,
            )
            await answer_callback_safe(query)
            return

        if action == "sk":
            res = await coordinator.manager.skip_match_character(
                match_id=match_id,
                player_id=user_id,
                expected_revision=current.draft_snapshot.revision,
                expected_generation=gen,
            )
            if not res.accepted or res.match is None:
                await answer_callback_safe(
                    query, _map_match_error(res.error_code, res.draft_error_code), show_alert=True
                )
                return
            await coordinator.sync_match_ui(
                res.match,
                update_board=True,
                update_card=True,
            )
            await answer_callback_safe(query)
            return

        if action == "as":
            role = index_to_role(args[2]) if len(args) >= 3 else None
            if role is None:
                await answer_callback_safe(query, "Invalid role.", show_alert=True)
                return
            res = await coordinator.manager.assign_match_role(
                match_id=match_id,
                player_id=user_id,
                role=role,
                expected_revision=current.draft_snapshot.revision,
                expected_generation=gen,
            )
            if not res.accepted or res.match is None:
                await answer_callback_safe(
                    query, _map_match_error(res.error_code, res.draft_error_code), show_alert=True
                )
                return
            if res.match.status is MatchLifecycleStatus.DRAFTING:
                coordinator.schedule_turn_timeout(res.match)
            await coordinator.sync_match_ui(
                res.match,
                update_board=True,
                update_card=True,
            )
            await answer_callback_safe(query)
            return

        if action == "cv":
            res = await coordinator.manager.claim_inactivity_victory(
                match_id=match_id, player_id=user_id, expected_generation=gen
            )
            if not res.accepted or res.match is None:
                await answer_callback_safe(
                    query, _map_match_error(res.error_code, res.draft_error_code), show_alert=True
                )
                return
            await coordinator.sync_match_ui(
                res.match,
                update_board=True,
                update_card=True,
            )
            await answer_callback_safe(query, "Victory claimed!")
            return

        if action == "ex":
            res = await coordinator.manager.grant_turn_extension(
                match_id=match_id, granting_player_id=user_id, expected_generation=gen
            )
            if not res.accepted or res.match is None:
                await answer_callback_safe(
                    query, _map_match_error(res.error_code, res.draft_error_code), show_alert=True
                )
                return
            coordinator.schedule_turn_timeout(res.match)
            await coordinator.sync_match_ui(
                res.match,
                update_board=True,
                update_card=True,
            )
            await answer_callback_safe(query, "Granted 60 more seconds.")
            return

    if action in {"gr", "grb", "grc", "gg"}:
        match_id = args[0] if args else ""
        match = coordinator.manager.get_match(match_id)
        if match is None or match.status is not MatchLifecycleStatus.DRAFTING:
            await answer_callback_safe(query, "This match has already ended.", show_alert=True)
            return
        if user_id not in match.players:
            await answer_callback_safe(query, "You are not a participant in this match.", show_alert=True)
            return

        if action == "gr":
            await edit_message_text_safe(
                coordinator.bot,
                chat_id=chat_id,
                message_id=msg_id,
                text=render_recover_confirmation(),
                reply_markup=build_recover_confirm_keyboard(match),
            )
            await answer_callback_safe(query)
            return

        if action == "grb":
            group_chat_id = coordinator.match_chat_id(match) or ""
            await edit_message_text_safe(
                coordinator.bot,
                chat_id=chat_id,
                message_id=msg_id,
                text=render_active_game(
                    match,
                    requester_id=user_id,
                    universe_name=coordinator.universe_name(match.universe_id),
                    player_names=coordinator.player_names_for_match(match),
                    group_title=coordinator.chat_title(group_chat_id) if group_chat_id else None,
                    group_link=coordinator.build_group_link(group_chat_id) if group_chat_id else None,
                ),
                reply_markup=build_active_game_keyboard(
                    match, game_link=coordinator.build_game_link(match)
                ),
            )
            await answer_callback_safe(query)
            return

        if action == "grc":
            gen = _parse_int(args[1]) if len(args) >= 2 else None
            if gen is None or gen != match.generation:
                await answer_callback_safe(
                    query,
                    "This gameplay interface is outdated.\nUse /game to access the latest match messages.",
                    show_alert=True,
                )
                return

        recovered = await coordinator.recover_game_ui(match, requester_id=user_id)
        if recovered is None:
            await edit_message_text_safe(
                coordinator.bot,
                chat_id=chat_id,
                message_id=msg_id,
                text=render_recover_failed(),
                reply_markup=None,
            )
            await answer_callback_safe(query, "Recovery could not be completed.", show_alert=True)
            return
        latest = coordinator.manager.get_match(match_id) or match
        group_chat_id = recovered.chat_id
        await edit_message_text_safe(
            coordinator.bot,
            chat_id=chat_id,
            message_id=msg_id,
            text=render_recover_success(
                group_title=coordinator.chat_title(group_chat_id),
                group_link=coordinator.build_group_link(group_chat_id),
            ),
            reply_markup=build_recover_success_keyboard(
                game_link=coordinator.build_game_link(latest)
            ),
        )
        await answer_callback_safe(query, "Match recovered!")
        return

    if action in {"gf", "gfc", "gfk"}:
        if len(args) < 2:
            await answer_callback_safe(query, "Invalid forfeit action.", show_alert=True)
            return
        match_id = args[0]
        gen = _parse_int(args[1])
        match = coordinator.manager.get_match(match_id)
        if match is None or match.status is not MatchLifecycleStatus.DRAFTING:
            await answer_callback_safe(query, "This match has already ended.", show_alert=True)
            return
        if user_id not in match.players:
            await answer_callback_safe(query, "You are not a participant in this match.", show_alert=True)
            return
        if gen is None or gen != match.generation:
            await answer_callback_safe(
                query,
                "This gameplay interface is outdated.\nUse /game to access the latest match messages.",
                show_alert=True,
            )
            return

        async with coordinator.forfeit_lock(match_id, user_id):
            latest_match = coordinator.manager.get_match(match_id)
            if latest_match is None or latest_match.status is not MatchLifecycleStatus.DRAFTING:
                await answer_callback_safe(query, "This match has already ended.", show_alert=True)
                return
            if gen != latest_match.generation:
                await answer_callback_safe(
                    query,
                    "This gameplay interface is outdated.\nUse /game to access the latest match messages.",
                    show_alert=True,
                )
                return

            if action == "gf":
                if msg.chat.type in {"group", "supergroup"}:
                    match_chat = coordinator.match_chat_id(latest_match)
                    if match_chat is not None and chat_id != match_chat:
                        await answer_callback_safe(
                            query,
                            "This gameplay interface is outdated.\nUse /game to access the latest match messages.",
                            show_alert=True,
                        )
                        return
                existing = coordinator.get_forfeit_confirmation(match_id, user_id)
                if existing is not None and existing[2] == latest_match.generation:
                    await answer_callback_safe(
                        query,
                        "You already have an open forfeit confirmation.",
                        show_alert=True,
                    )
                    return
                opp_id = (
                    latest_match.players[1]
                    if latest_match.players[0] == user_id
                    else latest_match.players[0]
                )
                sent = await send_message_safe(
                    coordinator.bot,
                    chat_id=chat_id,
                    text=render_forfeit_confirmation(
                        requester_id=user_id,
                        requester_name=coordinator.first_name(user_id),
                        opponent_id=opp_id,
                        opponent_name=coordinator.first_name(opp_id),
                    ),
                    reply_markup=build_forfeit_confirm_keyboard(latest_match, requester_id=user_id),
                )
                if sent is None:
                    await answer_callback_safe(
                        query,
                        "Could not open forfeit confirmation. Please try again.",
                        show_alert=True,
                    )
                    return
                coordinator.register_forfeit_confirmation(
                    match_id, user_id, str(sent.chat.id), sent.message_id, latest_match.generation
                )
                await coordinator.manager.attach_message_reference(
                    match_id,
                    MessageReference(
                        chat_id=str(sent.chat.id),
                        message_id=str(sent.message_id),
                        kind=f"fc:{user_id}",
                    ),
                )
                await answer_callback_safe(query)
                return

            requester_arg = args[2] if len(args) >= 3 else ""
            if requester_arg and user_id != requester_arg:
                await answer_callback_safe(
                    query,
                    "Only the player who requested this confirmation can respond.",
                    show_alert=True,
                )
                return

            existing = coordinator.get_forfeit_confirmation(match_id, user_id)
            if existing is None or (
                existing[0] != chat_id or existing[1] != msg_id or existing[2] != gen
            ):
                await answer_callback_safe(
                    query,
                    "This forfeit confirmation is no longer active.",
                    show_alert=True,
                )
                return
            # Consume registration before awaiting cancel/confirm to prevent cancel-vs-confirm races
            coordinator._forfeit_confirmations.pop((match_id, user_id), None)

            if action == "gfk":
                await coordinator._delete_or_strip_message(chat_id, msg_id)
                await answer_callback_safe(query, "Forfeit cancelled.")
                return

            res = await coordinator.manager.forfeit_match(
                match_id=match_id, player_id=user_id, expected_generation=gen
            )
            if not res.accepted or res.match is None:
                await answer_callback_safe(
                    query, _map_match_error(res.error_code, res.draft_error_code), show_alert=True
                )
                return
            await coordinator.sync_match_ui(
                res.match,
                update_board=True,
                update_card=True,
            )
            await answer_callback_safe(query, "You forfeited the match.")
            return

    # ------------------------------------------------------------------
    # Results: Battle Breakdown (Screen 11) & Back to Result
    # ------------------------------------------------------------------
    if action == "dr":
        if len(args) < 2:
            await answer_callback_safe(query, "Invalid details request.", show_alert=True)
            return
        match_id = args[0]
        idx = _parse_int(args[1])
        match = coordinator.manager.get_match(match_id)
        if match is None or idx is None:
            await answer_callback_safe(query, "Match details unavailable.", show_alert=True)
            return
        if user_id not in match.players:
            await answer_callback_safe(
                query,
                "Only match participants can view Battle Breakdown.",
                show_alert=True,
            )
            return
        await coordinator.show_detailed_results(
            match=match,
            viewer_id=user_id,
            role_index=max(0, min(idx, 6)),
            chat_id=chat_id,
            source_message_id=msg_id,
        )
        await answer_callback_safe(query)
        return

    if action == "mr":
        match_id = args[0] if args else ""
        match = coordinator.manager.get_match(match_id)
        if match is None:
            await answer_callback_safe(query, "Match not found.", show_alert=True)
            return
        if user_id not in match.players:
            await answer_callback_safe(
                query,
                "Only match participants can navigate match results.",
                show_alert=True,
            )
            return
        names = coordinator.player_names_for_match(match)
        await edit_message_text_safe(
            coordinator.bot,
            chat_id=chat_id,
            message_id=msg_id,
            text=render_match_results(
                match,
                universe_name=coordinator.universe_name(match.universe_id),
                player_names=names,
                char_lookup=coordinator.char_lookup_for_match(match),
            ),
            reply_markup=build_match_results_keyboard(match, player_names=names),
        )
        await answer_callback_safe(query)
        return

    if action == "rm":
        match_id = args[0] if args else ""
        match = coordinator.manager.get_match(match_id)
        if match is None:
            await answer_callback_safe(query, "Match not found.", show_alert=True)
            return
        if user_id not in match.players:
            await answer_callback_safe(query, "Only match participants may request a rematch.", show_alert=True)
            return
        opponent_id = match.players[1] if match.players[0] == user_id else match.players[0]
        res = await coordinator.manager.create_challenge(
            challenger_id=user_id,
            chat_id=chat_id,
            universe_id=match.universe_id,
            target_player_id=opponent_id,
            game_mode=match.game_mode,
        )
        if not res.accepted or res.challenge is None:
            await answer_callback_safe(query, _map_challenge_error(res.error_code), show_alert=True)
            return
        await coordinator.render_challenge_message(res.challenge, chat_id=chat_id)
        coordinator.schedule_challenge_expiry(res.challenge)
        await answer_callback_safe(query, "Rematch challenge sent!")
        return

    await answer_callback_safe(query, "Unknown action.", show_alert=True)


def build_callbacks_router() -> Router:
    r = Router(name="kayi_arena_callbacks")
    r.callback_query.register(handle_arena_callback, F.data.startswith("ka:"))
    return r
