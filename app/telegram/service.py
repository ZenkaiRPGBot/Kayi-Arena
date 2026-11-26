"""Application-to-Telegram UI coordinator for Kayi Arena (Module 6).

Connects Telegram commands and callbacks to MatchManager (Module 5),
CharacterDatabase (Module 4A), and Resolution (Module 3) while keeping
gameplay state strictly inside the application layer.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Mapping

from aiogram import Bot
from aiogram.types import Message, User

from app.database import CharacterDatabase, CharacterEntry, Universe
from app.engine import DraftPhase
from app.matches import (
    ChallengeOperationResult,
    ChallengeRecord,
    ChallengeStatus,
    ManagedMatch,
    MatchLifecycleStatus,
    MatchManager,
    MatchManagementErrorCode,
    MatchOperationResult,
    MessageReference,
)
from app.persistence.models import StartupRecoveryReport
from app.telegram.config import BotConfig
from app.telegram.constants import ROLE_ORDER
from app.telegram.media import CharacterMediaResolver
from app.telegram.keyboards import (
    build_awaiting_shuffle_keyboard,
    build_challenge_keyboard,
    build_character_revealed_keyboard,
    build_detailed_results_keyboard,
    build_draft_board_keyboard,
    build_inactivity_keyboard,
    build_match_results_keyboard,
)
from app.telegram.ports import ProfileStatsProvider, UnavailableStatsProvider
from app.telegram.safe_api import (
    edit_card_message_safe,
    edit_message_text_safe,
    send_message_safe,
    send_photo_or_text_safe,
)
from app.telegram.texts import (
    render_awaiting_shuffle_card,
    render_challenge_card,
    render_detailed_result_page,
    render_draft_board,
    render_match_results,
    render_retired_card_text,
    render_revealed_character_card,
    render_turn_expired_card,
)

if TYPE_CHECKING:
    from app.persistence.store import SqliteMatchStore

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class UniverseMenuContext:
    """Preserves reply-to-player context while navigating /arena menu."""

    owner_user_id: str
    target_player_id: str | None = None
    target_player_name: str | None = None
    game_mode: str = "ranked"
    page: int = 0


@dataclass(slots=True)
class MatchUIState:
    """Tracks the two primary Telegram messages for an active match."""

    chat_id: str
    board_message_id: int
    card_message_id: int
    card_is_photo: bool = False
    last_action_line: str | None = None


class ArenaTelegramCoordinator:
    """Coordinates Telegram rendering, timers, dedup, and MatchManager calls."""

    def __init__(
        self,
        *,
        bot: Bot,
        config: BotConfig,
        db: CharacterDatabase,
        manager: MatchManager,
        stats_provider: ProfileStatsProvider | None = None,
        store: SqliteMatchStore | None = None,
    ) -> None:
        self.bot = bot
        self.config = config
        self.db = db
        self.manager = manager
        self.stats_provider: ProfileStatsProvider = stats_provider or UnavailableStatsProvider()
        self.store = store
        self.media_resolver = CharacterMediaResolver(store)

        self._player_names: dict[str, str] = {}
        self._player_usernames: dict[str, str] = {}
        self._universe_menus: dict[tuple[str, int], UniverseMenuContext] = {}
        self._challenge_messages: dict[str, tuple[str, int]] = {}
        self._match_ui: dict[str, MatchUIState] = {}
        self._detail_messages: dict[tuple[str, int], tuple[str, str]] = {}
        self._seen_updates: dict[int, float] = {}
        self._timer_tasks: dict[str, asyncio.Task[None]] = {}
        self._recovery_locks: dict[str, asyncio.Lock] = {}
        self._char_cache: dict[str, CharacterEntry] = {}

    # ------------------------------------------------------------------
    # Player & Metadata Helpers
    # ------------------------------------------------------------------

    def register_user(self, user: User | None) -> str:
        if user is None:
            return ""
        uid = str(user.id)
        name = (user.full_name or user.first_name or user.username or uid).strip()
        self._player_names[uid] = name
        if user.username:
            self._player_usernames[uid] = user.username
        if self.store is not None:
            self.store.upsert_player_profile(uid, name, user.username)
        return uid

    def display_name(self, player_id: str) -> str:
        return self._player_names.get(player_id, player_id)

    def player_names_for_match(self, match: ManagedMatch) -> dict[str, str]:
        return {pid: self.display_name(pid) for pid in match.players}

    def universe_name(self, universe_id: str) -> str:
        try:
            return self.db.get_universe(universe_id).name
        except Exception:
            return universe_id

    def eligible_universes(self) -> tuple[Universe, ...]:
        return self.db.list_eligible_universes(kind=self.config.dataset_kind)

    def get_character_entry(self, character_id: str) -> CharacterEntry | None:
        cached = self._char_cache.get(character_id)
        if cached is not None:
            return cached
        try:
            rec = self.db.get_character_entry(character_id)
        except Exception:
            return None
        self._char_cache[character_id] = rec
        return rec

    def char_lookup_for_match(self, match: ManagedMatch) -> dict[str, CharacterEntry]:
        lookup: dict[str, CharacterEntry] = {}
        for pid in match.players:
            for cid in match.public_view.teams[pid].values():
                if cid is not None:
                    rec = self.get_character_entry(cid)
                    if rec is not None:
                        lookup[cid] = rec
        return lookup

    def is_duplicate_update(self, update_id: int) -> bool:
        now = self.manager.clock()
        if len(self._seen_updates) > 2000:
            cutoff = now - 600.0
            self._seen_updates = {k: v for k, v in self._seen_updates.items() if v >= cutoff}
        if update_id in self._seen_updates:
            return True
        self._seen_updates[update_id] = now
        return False

    # ------------------------------------------------------------------
    # Universe Menu Context
    # ------------------------------------------------------------------

    def save_universe_menu(
        self,
        chat_id: str,
        message_id: int,
        ctx: UniverseMenuContext,
    ) -> None:
        self._universe_menus[(chat_id, message_id)] = ctx

    def get_universe_menu(self, chat_id: str, message_id: int) -> UniverseMenuContext | None:
        return self._universe_menus.get((chat_id, message_id))

    # ------------------------------------------------------------------
    # Challenge Lifecycle & Rendering
    # ------------------------------------------------------------------

    def register_challenge_message(self, challenge_id: str, chat_id: str, message_id: int) -> None:
        self._challenge_messages[challenge_id] = (chat_id, message_id)
        if self.store is not None:
            self.store.set_challenge_message(challenge_id, chat_id, str(message_id))

    async def render_challenge_message(
        self,
        challenge: ChallengeRecord,
        *,
        chat_id: str,
        message_id: int | None = None,
    ) -> Message | None:
        now = self.manager.clock()
        remaining = max(0.0, challenge.expires_at - now)
        text = render_challenge_card(
            challenge,
            universe_name=self.universe_name(challenge.universe_id),
            challenger_name=self.display_name(challenge.challenger_id),
            target_name=(
                self.display_name(challenge.target_player_id)
                if challenge.target_player_id
                else None
            ),
            seconds_remaining=remaining,
        )
        markup = build_challenge_keyboard(challenge)
        if message_id is not None:
            await edit_message_text_safe(
                self.bot,
                chat_id=chat_id,
                message_id=message_id,
                text=text,
                reply_markup=markup,
            )
            return None
        sent = await send_message_safe(
            self.bot,
            chat_id=chat_id,
            text=text,
            reply_markup=markup,
        )
        if sent is not None:
            self.register_challenge_message(challenge.challenge_id, str(sent.chat.id), sent.message_id)
        return sent

    def schedule_challenge_expiry(self, challenge: ChallengeRecord) -> None:
        key = f"chl:{challenge.challenge_id}"
        self._cancel_timer(key)
        delay = max(0.0, challenge.expires_at - self.manager.clock())

        async def _expire() -> None:
            try:
                await asyncio.sleep(delay)
                res = await self.manager.expire_challenge(challenge.challenge_id)
                if res.accepted and res.challenge is not None:
                    loc = self._challenge_messages.get(challenge.challenge_id)
                    if loc is not None:
                        await self.render_challenge_message(
                            res.challenge, chat_id=loc[0], message_id=loc[1]
                        )
            except asyncio.CancelledError:
                return
            except Exception:
                logger.exception("Error expiring challenge %s", challenge.challenge_id)

        self._timer_tasks[key] = asyncio.create_task(_expire(), name=key)

    # ------------------------------------------------------------------
    # Active Match Rendering (2-message architecture)
    # ------------------------------------------------------------------

    def _character_media_ref(self, rec: CharacterEntry | None) -> str | None:
        return self.media_resolver.resolve_media_ref(rec)

    async def start_match_ui(self, match: ManagedMatch, *, chat_id: str) -> MatchUIState | None:
        """Send the two primary messages (board + card) for a newly started match."""
        names = self.player_names_for_match(match)
        u_name = self.universe_name(match.universe_id)
        char_lookup = self.char_lookup_for_match(match)
        remaining = max(0.0, match.turn_deadline_at - self.manager.clock())

        board_msg = await send_message_safe(
            self.bot,
            chat_id=chat_id,
            text=render_draft_board(
                match,
                universe_name=u_name,
                player_names=names,
                char_lookup=char_lookup,
                seconds_remaining=remaining,
                last_action_line="Match started!",
            ),
            reply_markup=build_draft_board_keyboard(match),
        )
        if board_msg is None:
            return None

        card_caption = render_awaiting_shuffle_card(match, player_names=names)
        card_msg, is_photo = await send_photo_or_text_safe(
            self.bot,
            chat_id=chat_id,
            photo=self.config.card_back_ref or None,
            caption=card_caption,
            reply_markup=build_awaiting_shuffle_keyboard(match),
        )
        if card_msg is None:
            return None

        state = MatchUIState(
            chat_id=str(board_msg.chat.id),
            board_message_id=board_msg.message_id,
            card_message_id=card_msg.message_id,
            card_is_photo=is_photo,
            last_action_line="Match started!",
        )
        self._match_ui[match.match_id] = state
        await self.manager.attach_message_reference(
            match.match_id,
            MessageReference(chat_id=state.chat_id, message_id=str(state.board_message_id), kind="board"),
        )
        await self.manager.attach_message_reference(
            match.match_id,
            MessageReference(chat_id=state.chat_id, message_id=str(state.card_message_id), kind="card"),
        )
        self.schedule_turn_timeout(match)
        return state

    async def sync_match_ui(
        self,
        match: ManagedMatch,
        *,
        last_action_line: str | None = None,
        update_board: bool = True,
        update_card: bool = True,
    ) -> None:
        """Project authoritative ManagedMatch state onto the two primary messages."""
        state = self._match_ui.get(match.match_id)
        if state is None:
            return
        if last_action_line is not None:
            state.last_action_line = last_action_line

        names = self.player_names_for_match(match)
        u_name = self.universe_name(match.universe_id)

        if match.status is not MatchLifecycleStatus.DRAFTING:
            self._cancel_match_timers(match.match_id)
            if update_board:
                char_lookup = self.char_lookup_for_match(match)
                await edit_message_text_safe(
                    self.bot,
                    chat_id=state.chat_id,
                    message_id=state.board_message_id,
                    text=render_match_results(
                        match,
                        universe_name=u_name,
                        player_names=names,
                        char_lookup=char_lookup,
                    ),
                    reply_markup=build_match_results_keyboard(match, player_names=names),
                )
            if update_card:
                retired_text = render_retired_card_text(match, player_names=names)
                _, state.card_is_photo = await edit_card_message_safe(
                    self.bot,
                    chat_id=state.chat_id,
                    message_id=state.card_message_id,
                    is_photo=state.card_is_photo,
                    photo=None,
                    caption=retired_text,
                    reply_markup=None,
                )
            return

        if update_board:
            char_lookup = self.char_lookup_for_match(match)
            remaining = max(0.0, match.turn_deadline_at - self.manager.clock())
            await edit_message_text_safe(
                self.bot,
                chat_id=state.chat_id,
                message_id=state.board_message_id,
                text=render_draft_board(
                    match,
                    universe_name=u_name,
                    player_names=names,
                    char_lookup=char_lookup,
                    seconds_remaining=remaining,
                    last_action_line=state.last_action_line,
                ),
                reply_markup=build_draft_board_keyboard(match),
            )

        if update_card:
            if match.inactivity_claim_offered_to is not None:
                caption = render_turn_expired_card(match, player_names=names)
                markup = build_inactivity_keyboard(match)
                photo = self.config.card_back_ref or None
            elif match.draft_snapshot.phase is DraftPhase.AWAITING_SHUFFLE:
                caption = render_awaiting_shuffle_card(match, player_names=names)
                markup = build_awaiting_shuffle_keyboard(match)
                photo = self.config.card_back_ref or None
            else:
                held = match.draft_snapshot.held_character
                rec = (
                    self.get_character_entry(held.character_id)
                    if held is not None
                    else None
                )
                if rec is not None:
                    caption = render_revealed_character_card(
                        match,
                        character=rec,
                        universe_name=u_name,
                        player_names=names,
                    )
                    photo = self._character_media_ref(rec)
                else:
                    cid = held.character_id if held else "Unknown"
                    caption = f"<b>{cid}</b>\n\nChoose a role."
                    photo = None
                markup = build_character_revealed_keyboard(match)

            _, state.card_is_photo = await edit_card_message_safe(
                self.bot,
                chat_id=state.chat_id,
                message_id=state.card_message_id,
                is_photo=state.card_is_photo,
                photo=photo,
                caption=caption,
                reply_markup=markup,
                fallback_photo=self.config.card_back_ref or None,
            )

    def _recovery_lock(self, match_id: str) -> asyncio.Lock:
        lock = self._recovery_locks.get(match_id)
        if lock is None:
            lock = asyncio.Lock()
            self._recovery_locks[match_id] = lock
        return lock

    async def recover_on_startup(self) -> StartupRecoveryReport:
        """Restore persisted challenges, matches, UI references, and timers."""
        if self.store is not None:
            self._player_names.update(self.store.load_player_names())

        (
            report,
            pending_challenges,
            expired_challenges,
            restored_matches,
            inactivity_prompted,
            abandoned_matches,
        ) = await self.manager.recover_from_store()

        for chl, msg_id in expired_challenges:
            if msg_id is not None:
                await self.render_challenge_message(
                    chl, chat_id=chl.chat_id, message_id=int(msg_id)
                )

        for chl, msg_id in pending_challenges:
            if msg_id is not None:
                self._challenge_messages[chl.challenge_id] = (chl.chat_id, int(msg_id))
            self.schedule_challenge_expiry(chl)

        prompted_ids = {m.match_id for m in inactivity_prompted}
        for match in restored_matches:
            self._restore_match_ui_from_refs(match)
            if match.match_id in prompted_ids:
                await self.sync_match_ui(
                    match,
                    last_action_line="Turn expired while bot was offline — awaiting opponent decision.",
                    update_board=True,
                    update_card=True,
                )
                self.schedule_claim_window_timeout(match)
            elif match.inactivity_claim_offered_to is not None:
                self.schedule_claim_window_timeout(match)
            else:
                self.schedule_turn_timeout(match)

        for match in abandoned_matches:
            self._restore_match_ui_from_refs(match)
            await self.sync_match_ui(
                match,
                last_action_line="Match abandoned due to mutual inactivity during downtime.",
                update_board=True,
                update_card=True,
            )

        return report

    def _restore_match_ui_from_refs(self, match: ManagedMatch) -> MatchUIState | None:
        board_ref = next((r for r in reversed(match.message_refs) if r.kind == "board"), None)
        card_ref = next((r for r in reversed(match.message_refs) if r.kind == "card"), None)
        if board_ref is None or card_ref is None:
            return None
        state = MatchUIState(
            chat_id=board_ref.chat_id,
            board_message_id=int(board_ref.message_id),
            card_message_id=int(card_ref.message_id),
            card_is_photo=False,
        )
        self._match_ui[match.match_id] = state
        return state

    async def recover_game_ui(self, match: ManagedMatch) -> MatchUIState | None:
        """Reconstruct missing/unusable messages in original chat & invalidate old controls."""
        async with self._recovery_lock(match.match_id):
            latest = self.manager.get_match(match.match_id) or match
            state = self._match_ui.get(latest.match_id) or self._restore_match_ui_from_refs(latest)
            if state is None:
                return None

            names = self.player_names_for_match(latest)
            u_name = self.universe_name(latest.universe_id)
            char_lookup = self.char_lookup_for_match(latest)
            remaining = max(0.0, latest.turn_deadline_at - self.manager.clock())

            # Bump generation FIRST so obsolete controls cannot mutate the match
            refs_res = await self.manager.replace_message_references(
                latest.match_id, latest.message_refs, bump_generation=True
            )
            if not refs_res.accepted or refs_res.match is None:
                return None
            latest = refs_res.match

            board_text = render_draft_board(
                latest,
                universe_name=u_name,
                player_names=names,
                char_lookup=char_lookup,
                seconds_remaining=remaining,
                last_action_line="Game recovered.",
            )
            board_markup = build_draft_board_keyboard(latest)

            if latest.inactivity_claim_offered_to is not None:
                caption = render_turn_expired_card(latest, player_names=names)
                markup = build_inactivity_keyboard(latest)
                photo = self.config.card_back_ref or None
            elif latest.draft_snapshot.phase is DraftPhase.AWAITING_SHUFFLE:
                caption = render_awaiting_shuffle_card(latest, player_names=names)
                markup = build_awaiting_shuffle_keyboard(latest)
                photo = self.config.card_back_ref or None
            else:
                held = latest.draft_snapshot.held_character
                rec = (
                    self.get_character_entry(held.character_id)
                    if held is not None
                    else None
                )
                caption = (
                    render_revealed_character_card(
                        latest, character=rec, universe_name=u_name, player_names=names
                    )
                    if rec is not None
                    else "Choose a role."
                )
                photo = self._character_media_ref(rec)
                markup = build_character_revealed_keyboard(latest)

            # Reuse surviving board/card if still editable; recreate only missing/unusable ones
            board_ok = await edit_message_text_safe(
                self.bot,
                chat_id=state.chat_id,
                message_id=state.board_message_id,
                text=board_text,
                reply_markup=board_markup,
            )
            board_msg_id = state.board_message_id
            if not board_ok:
                new_board = await send_message_safe(
                    self.bot,
                    chat_id=state.chat_id,
                    text=board_text,
                    reply_markup=board_markup,
                )
                if new_board is None:
                    return None
                board_msg_id = new_board.message_id

            card_ok, is_photo = await edit_card_message_safe(
                self.bot,
                chat_id=state.chat_id,
                message_id=state.card_message_id,
                is_photo=state.card_is_photo,
                photo=photo,
                caption=caption,
                reply_markup=markup,
                fallback_photo=self.config.card_back_ref or None,
            )
            card_msg_id = state.card_message_id
            if not card_ok:
                new_card, is_photo = await send_photo_or_text_safe(
                    self.bot,
                    chat_id=state.chat_id,
                    photo=photo,
                    caption=caption,
                    reply_markup=markup,
                    fallback_photo=self.config.card_back_ref or None,
                )
                if new_card is None:
                    return None
                card_msg_id = new_card.message_id

            new_state = MatchUIState(
                chat_id=state.chat_id,
                board_message_id=board_msg_id,
                card_message_id=card_msg_id,
                card_is_photo=is_photo,
                last_action_line="Game recovered.",
            )
            self._match_ui[latest.match_id] = new_state
            await self.manager.replace_message_references(
                latest.match_id,
                (
                    MessageReference(chat_id=new_state.chat_id, message_id=str(board_msg_id), kind="board"),
                    MessageReference(chat_id=new_state.chat_id, message_id=str(card_msg_id), kind="card"),
                ),
                bump_generation=False,
            )
            return new_state

    def build_game_link(self, match: ManagedMatch) -> str | None:
        state = self._match_ui.get(match.match_id)
        if state is None:
            return None
        try:
            cid = int(state.chat_id)
        except ValueError:
            return None
        # Telegram c/<internal_id>/<msg_id> links work for supergroups/channels (-100...)
        if cid < -1000000000000:
            internal = str(abs(cid) - 1000000000000)
            return f"https://t.me/c/{internal}/{state.board_message_id}"
        return None

    # ------------------------------------------------------------------
    # Viewer-Specific Detailed Results
    # ------------------------------------------------------------------

    async def show_detailed_results(
        self,
        *,
        match: ManagedMatch,
        viewer_id: str,
        role_index: int,
        chat_id: str,
        source_message_id: int,
    ) -> None:
        names = self.player_names_for_match(match)
        char_lookup = self.char_lookup_for_match(match)
        text = render_detailed_result_page(
            match, role_index=role_index, player_names=names, char_lookup=char_lookup
        )
        markup = build_detailed_results_keyboard(match.match_id, role_index)

        owner_info = self._detail_messages.get((chat_id, source_message_id))
        if owner_info is not None and owner_info[0] == viewer_id and owner_info[1] == match.match_id:
            await edit_message_text_safe(
                self.bot,
                chat_id=chat_id,
                message_id=source_message_id,
                text=text,
                reply_markup=markup,
            )
            return

        sent = await send_message_safe(
            self.bot,
            chat_id=chat_id,
            text=text,
            reply_markup=markup,
        )
        if sent is not None:
            self._detail_messages[(str(sent.chat.id), sent.message_id)] = (viewer_id, match.match_id)

    def is_viewer_detail_message(self, chat_id: str, message_id: int, viewer_id: str) -> bool:
        info = self._detail_messages.get((chat_id, message_id))
        return info is not None and info[0] == viewer_id

    # ------------------------------------------------------------------
    # Timers
    # ------------------------------------------------------------------

    def _cancel_timer(self, key: str) -> None:
        task = self._timer_tasks.pop(key, None)
        if task is not None and not task.done():
            task.cancel()

    def _cancel_match_timers(self, match_id: str) -> None:
        self._cancel_timer(f"turn:{match_id}")
        self._cancel_timer(f"claim:{match_id}")

    def schedule_turn_timeout(self, match: ManagedMatch) -> None:
        key = f"turn:{match.match_id}"
        self._cancel_timer(key)
        if match.status is not MatchLifecycleStatus.DRAFTING:
            return
        delay = max(0.0, match.turn_deadline_at - self.manager.clock())
        expected_rev = match.draft_snapshot.revision
        expected_turn = match.turn_number_at_start

        async def _on_turn_expire() -> None:
            try:
                await asyncio.sleep(delay)
                res = await self.manager.handle_turn_timeout(
                    match_id=match.match_id,
                    expected_revision=expected_rev,
                    expected_turn_number=expected_turn,
                )
                if res.accepted and res.match is not None:
                    await self.sync_match_ui(
                        res.match,
                        last_action_line="Turn expired — awaiting opponent decision.",
                        update_board=True,
                        update_card=True,
                    )
                    self.schedule_claim_window_timeout(res.match)
            except asyncio.CancelledError:
                return
            except Exception:
                logger.exception("Error handling turn timeout for %s", match.match_id)

        self._timer_tasks[key] = asyncio.create_task(_on_turn_expire(), name=key)

    def schedule_claim_window_timeout(self, match: ManagedMatch) -> None:
        key = f"claim:{match.match_id}"
        self._cancel_timer(key)
        if match.inactivity_claim_expires_at is None:
            return
        delay = max(0.0, match.inactivity_claim_expires_at - self.manager.clock())
        expected_gen = match.generation

        async def _on_claim_expire() -> None:
            try:
                await asyncio.sleep(delay)
                res = await self.manager.handle_claim_window_timeout(
                    match_id=match.match_id,
                    expected_generation=expected_gen,
                )
                if res.accepted and res.match is not None:
                    await self.sync_match_ui(
                        res.match,
                        last_action_line="Match abandoned due to mutual inactivity.",
                        update_board=True,
                        update_card=True,
                    )
            except asyncio.CancelledError:
                return
            except Exception:
                logger.exception("Error handling claim timeout for %s", match.match_id)

        self._timer_tasks[key] = asyncio.create_task(_on_claim_expire(), name=key)

    async def shutdown(self) -> None:
        for key in list(self._timer_tasks):
            self._cancel_timer(key)
