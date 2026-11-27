"""Callback query handlers for Kayi Arena with strict authorization & generation checks."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.types import CallbackQuery

from app.engine import ErrorCode as DraftErrorCode
from app.matches import MatchLifecycleStatus, MatchManagementErrorCode
from app.telegram.callbacks import code_to_rarity, decode_cb, index_to_role
from app.telegram.constants import CATALOGUE_PER_PAGE, LEADERBOARD_PER_PAGE
from app.telegram.keyboards import (
    build_active_game_keyboard,
    build_catalogue_page_keyboard,
    build_catalogue_universes_keyboard,
    build_forfeit_confirm_keyboard,
    build_help_keyboard,
    build_history_keyboard,
    build_home_keyboard,
    build_leaderboard_keyboard,
    build_match_results_keyboard,
    build_profile_keyboard,
    build_support_keyboard,
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
    render_support_home,
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
    if code is MatchManagementErrorCode.STALE_CONTROL_GENERATION:
        return "This action has expired."
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
    if draft_code is DraftErrorCode.STALE_REVISION:
        return "This action has expired."
    return "Action could not be completed."


def _map_challenge_error(code: MatchManagementErrorCode | None) -> str:
    if code is MatchManagementErrorCode.SELF_CHALLENGE_FORBIDDEN:
        return "You cannot accept your own challenge."
    if code is MatchManagementErrorCode.NOT_CHALLENGE_TARGET:
        return "This direct challenge is for another player."
    if code is MatchManagementErrorCode.NOT_CHALLENGER:
        return "Only the challenger can do that."
    if code is MatchManagementErrorCode.PLAYER_ALREADY_IN_MATCH:
        return "You already have an active match."
    if code in {
        MatchManagementErrorCode.CHALLENGE_EXPIRED,
        MatchManagementErrorCode.CHALLENGE_NOT_OPEN,
        MatchManagementErrorCode.STALE_CONTROL_GENERATION,
        MatchManagementErrorCode.CHALLENGE_NOT_FOUND,
    }:
        return "This action has expired."
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
    # Universe Selection (/arena menu)
    # ------------------------------------------------------------------
    if action == "arena":
        universes = coordinator.eligible_universes()
        coordinator.save_universe_menu(
            chat_id,
            msg_id,
            UniverseMenuContext(owner_user_id=user_id, game_mode="ranked", page=0),
        )
        await edit_message_text_safe(
            coordinator.bot,
            chat_id=chat_id,
            message_id=msg_id,
            text=render_universe_selection(universes=universes, game_mode="ranked"),
            reply_markup=build_universe_selection_keyboard(
                universes=universes, page=0, game_mode="ranked"
            ),
        )
        await answer_callback_safe(query)
        return

    if action in {"um", "u"}:
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
    # Challenge Actions: Accept, Mode Switch, Cancel
    # ------------------------------------------------------------------
    if action in {"ca", "cm", "cx"}:
        if len(args) < 2:
            await answer_callback_safe(query, "Invalid challenge action.", show_alert=True)
            return
        challenge_id = args[0]
        gen = _parse_int(args[1])
        if gen is None:
            await answer_callback_safe(query, "Invalid challenge state.", show_alert=True)
            return

        if action == "ca":
            res = await coordinator.manager.accept_challenge(
                challenge_id=challenge_id,
                player_id=user_id,
                expected_generation=gen,
            )
            if not res.accepted or res.challenge is None or res.match is None:
                await answer_callback_safe(query, _map_challenge_error(res.error_code), show_alert=True)
                return
            await coordinator.render_challenge_message(
                res.challenge, chat_id=chat_id, message_id=msg_id
            )
            await coordinator.start_match_ui(res.match, chat_id=chat_id)
            await answer_callback_safe(query, "Challenge accepted!")
            return

        if action == "cm":
            res = await coordinator.manager.switch_challenge_mode(
                challenge_id=challenge_id,
                player_id=user_id,
                expected_generation=gen,
            )
            if not res.accepted or res.challenge is None:
                await answer_callback_safe(query, _map_challenge_error(res.error_code), show_alert=True)
                return
            await coordinator.render_challenge_message(
                res.challenge, chat_id=chat_id, message_id=msg_id
            )
            await answer_callback_safe(query, f"Mode set to {res.challenge.game_mode.title()}.")
            return

        res = await coordinator.manager.cancel_challenge(
            challenge_id=challenge_id,
            player_id=user_id,
            expected_generation=gen,
        )
        if not res.accepted or res.challenge is None:
            await answer_callback_safe(query, _map_challenge_error(res.error_code), show_alert=True)
            return
        await coordinator.render_challenge_message(res.challenge, chat_id=chat_id, message_id=msg_id)
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

        if action == "sh":
            current = coordinator.manager.get_match(match_id)
            if current is None:
                await answer_callback_safe(query, "Match not found.", show_alert=True)
                return
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
                last_action_line=f"{coordinator.display_name(user_id)} shuffled a character.",
                update_board=False,
                update_card=True,
            )
            await answer_callback_safe(query)
            return

        if action == "sk":
            current = coordinator.manager.get_match(match_id)
            if current is None:
                await answer_callback_safe(query, "Match not found.", show_alert=True)
                return
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
                last_action_line=f"{coordinator.display_name(user_id)} skipped their character.",
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
            current = coordinator.manager.get_match(match_id)
            if current is None:
                await answer_callback_safe(query, "Match not found.", show_alert=True)
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
                last_action_line=f"{coordinator.display_name(user_id)} assigned {role}.",
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
                last_action_line=f"{coordinator.display_name(user_id)} claimed victory by inactivity.",
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
                last_action_line=f"{coordinator.display_name(user_id)} granted +60s extension.",
                update_board=True,
                update_card=True,
            )
            await answer_callback_safe(query, "Granted 60 more seconds.")
            return

    if action == "gg":
        match_id = args[0] if args else ""
        match = coordinator.manager.get_match(match_id)
        if match is None or match.status is not MatchLifecycleStatus.DRAFTING:
            await answer_callback_safe(query, "Match is no longer active.", show_alert=True)
            return
        if user_id not in match.players:
            await answer_callback_safe(query, "You are not a participant in this match.", show_alert=True)
            return
        recovered = await coordinator.recover_game_ui(match)
        if recovered is None:
            await answer_callback_safe(query, "Unable to recover match messages.", show_alert=True)
            return
        await answer_callback_safe(query, "Game recovered!")
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
            await answer_callback_safe(query, "This action has expired.", show_alert=True)
            return

        if action == "gf":
            await edit_message_text_safe(
                coordinator.bot,
                chat_id=chat_id,
                message_id=msg_id,
                text=render_forfeit_confirmation(),
                reply_markup=build_forfeit_confirm_keyboard(match),
            )
            await answer_callback_safe(query)
            return

        if action == "gfk":
            await edit_message_text_safe(
                coordinator.bot,
                chat_id=chat_id,
                message_id=msg_id,
                text=render_active_game(
                    match,
                    requester_id=user_id,
                    universe_name=coordinator.universe_name(match.universe_id),
                    player_names=coordinator.player_names_for_match(match),
                ),
                reply_markup=build_active_game_keyboard(
                    match, game_link=coordinator.build_game_link(match)
                ),
            )
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
        await edit_message_text_safe(
            coordinator.bot,
            chat_id=chat_id,
            message_id=msg_id,
            text="🏳️ Match forfeited.",
            reply_markup=None,
        )
        await coordinator.sync_match_ui(
            res.match,
            last_action_line=f"{coordinator.display_name(user_id)} forfeited.",
            update_board=True,
            update_card=True,
        )
        await answer_callback_safe(query, "You forfeited the match.")
        return

    # ------------------------------------------------------------------
    # Results: Detailed Results & Rematch
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
        if coordinator.is_viewer_detail_message(chat_id, msg_id, user_id):
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
