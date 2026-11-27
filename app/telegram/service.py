"""Application-to-Telegram UI coordinator for Kayi Arena (Module 6).

Connects Telegram commands and callbacks to MatchManager (Module 5),
CharacterDatabase (Module 4A), and Resolution (Module 3) while keeping
gameplay state strictly inside the application layer.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
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
    replace_text_with_photo_card_safe,
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
    """Preserves battle configuration & challenge target while navigating /arena."""

    owner_user_id: str
    chat_id: str = ""
    target_player_id: str | None = None
    target_player_name: str | None = None
    selected_universe_id: str | None = None
    explicit_universe_mode: bool = False
    game_mode: str = "ranked"
    page: int = 0
    screen: str = "config"
    invalid_universe_arg: str | None = None
    created_at: float = 0.0
    cancelled: bool = False
    confirmed: bool = False


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
        self._started_at: float = time.monotonic()
        self._maintenance_mode: bool = (
            store.get_setting("maintenance_mode", "0") == "1" if store is not None else False
        )
        self._broadcast_compose: set[str] = set()
        self._broadcast_drafts: dict[str, str] = {}
        self._admin_input_state: dict[str, tuple[str, str]] = {}
        self._welcome_video_override: str | None = None
        self._handbook_illustrations: dict[str, str] = {}
        self._handbook_owners: dict[tuple[str, int], str] = {}
        self._char_browser_filters: dict[str, dict[str, str]] = {}
        self._latency_samples: deque[float] = deque(maxlen=100)

    def record_latency_ms(self, ms: float) -> None:
        if ms >= 0.0:
            self._latency_samples.append(float(ms))

    def latency_percentiles(self) -> dict[str, float] | None:
        if len(self._latency_samples) < 2:
            return None
        ordered = sorted(self._latency_samples)
        n = len(ordered)
        return {
            "median": ordered[n // 2],
            "p95": ordered[min(n - 1, int(0.95 * (n - 1)))],
            "p99": ordered[min(n - 1, int(0.99 * (n - 1)))],
            "count": float(n),
        }

    def uptime_seconds(self) -> float:
        return max(0.0, time.monotonic() - self._started_at)

    def is_maintenance_mode(self) -> bool:
        return self._maintenance_mode

    def set_maintenance_mode(self, enabled: bool) -> None:
        self._maintenance_mode = bool(enabled)
        if self.store is not None:
            self.store.set_setting("maintenance_mode", "1" if enabled else "0")

    def begin_broadcast_compose(self, admin_id: str) -> None:
        self._broadcast_compose.add(admin_id)
        self._broadcast_drafts.pop(admin_id, None)

    def is_awaiting_broadcast(self, admin_id: str) -> bool:
        return admin_id in self._broadcast_compose

    def set_broadcast_draft(self, admin_id: str, text: str) -> None:
        self._broadcast_compose.discard(admin_id)
        self._broadcast_drafts[admin_id] = text

    def pop_broadcast_draft(self, admin_id: str) -> str | None:
        self._broadcast_compose.discard(admin_id)
        return self._broadcast_drafts.pop(admin_id, None)

    def clear_broadcast_state(self, admin_id: str) -> None:
        self._broadcast_compose.discard(admin_id)
        self._broadcast_drafts.pop(admin_id, None)

    def set_admin_input_state(self, admin_id: str, mode: str, target_id: str = "") -> None:
        self._admin_input_state[admin_id] = (mode, target_id)

    def get_admin_input_state(self, admin_id: str) -> tuple[str, str] | None:
        return self._admin_input_state.get(admin_id)

    def clear_admin_input_state(self, admin_id: str) -> None:
        self._admin_input_state.pop(admin_id, None)

    def get_char_browser_filter(self, admin_id: str, universe_id: str) -> dict[str, str]:
        flt = self._char_browser_filters.get(admin_id)
        if flt is None or flt.get("universe_id") != universe_id:
            flt = {
                "universe_id": universe_id,
                "status": "all",
                "rarity": "all",
                "image": "all",
                "query": "",
            }
            self._char_browser_filters[admin_id] = flt
        return flt

    def set_char_browser_filter(self, admin_id: str, universe_id: str, **updates: str) -> dict[str, str]:
        flt = self.get_char_browser_filter(admin_id, universe_id)
        flt.update(updates)
        return flt

    def get_welcome_video_file_id(self) -> str:
        if self._welcome_video_override is not None:
            return self._welcome_video_override
        if self.store is not None:
            val = self.store.get_setting("welcome_video_file_id", "")
            if val:
                return val
        return self.config.welcome_video_file_id

    def set_welcome_video_file_id(self, file_id: str) -> None:
        cleaned = file_id.strip()
        self._welcome_video_override = cleaned
        if self.store is not None:
            self.store.set_setting("welcome_video_file_id", cleaned)

    _HANDBOOK_SETTING_KEYS: dict[str, str] = {
        "menu": "handbook_cover_file_id",
        "1": "handbook_ch1_file_id",
        "2": "handbook_ch2_file_id",
        "3": "handbook_ch3_file_id",
        "4": "handbook_ch4_file_id",
        "5": "handbook_ch5_file_id",
        "6": "handbook_ch6_file_id",
    }

    def get_handbook_illustration_file_id(self, page: str) -> str:
        key = self._HANDBOOK_SETTING_KEYS.get(page)
        if not key:
            return ""
        if page in self._handbook_illustrations:
            return self._handbook_illustrations[page]
        if self.store is not None:
            val = self.store.get_setting(key, "")
            if val:
                return val
        return ""

    def set_handbook_illustration_file_id(self, page: str, file_id: str) -> None:
        key = self._HANDBOOK_SETTING_KEYS.get(page)
        if not key:
            raise ValueError(f"Unknown handbook page: {page!r}")
        cleaned = file_id.strip()
        self._handbook_illustrations[page] = cleaned
        if self.store is not None:
            self.store.set_setting(key, cleaned)

    def register_handbook_message(self, chat_id: int | str, message_id: int, owner_id: str) -> None:
        if len(self._handbook_owners) > 1000:
            oldest = next(iter(self._handbook_owners))
            self._handbook_owners.pop(oldest, None)
        self._handbook_owners[(str(chat_id), int(message_id))] = owner_id

    def get_handbook_owner(self, chat_id: int | str, message_id: int) -> str | None:
        return self._handbook_owners.get((str(chat_id), int(message_id)))

    def register_chat(self, chat_id: int | str, chat_type: str, title: str | None = None) -> None:
        if self.store is not None:
            self.store.upsert_known_chat(str(chat_id), chat_type, title)

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
        if universe_id.strip().lower() == "random":
            return "Random"
        try:
            return self.db.get_universe(universe_id).name
        except Exception:
            return universe_id

    def eligible_universes(self) -> tuple[Universe, ...]:
        items = list(self.db.list_eligible_universes(kind=self.config.dataset_kind))
        items.sort(key=lambda u: (u.name.lower(), u.universe_id))
        return tuple(items)

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
        if len(self._universe_menus) > 500:
            oldest = next(iter(self._universe_menus))
            self._universe_menus.pop(oldest, None)
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

    async def _character_media_photo_async(self, rec: CharacterEntry | None) -> Any:
        return await self.media_resolver.resolve_card_photo_async(
            self.bot,
            rec,
            channel_id=self.config.media_channel_id,
            bot_username=self.config.bot_username,
        )

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
            self._recovery_locks.pop(match.match_id, None)
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
            rec: CharacterEntry | None = None
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
                    photo = await self._character_media_photo_async(rec)
                else:
                    cid = held.character_id if held else "Unknown"
                    caption = f"<b>{cid}</b>\n\nChoose a role."
                    photo = None
                markup = build_character_revealed_keyboard(match)

            if not state.card_is_photo and photo is not None:
                sent_card, now_is_photo = await replace_text_with_photo_card_safe(
                    self.bot,
                    chat_id=state.chat_id,
                    old_message_id=state.card_message_id,
                    photo=photo,
                    caption=caption,
                    reply_markup=markup,
                    fallback_photo=self.config.card_back_ref or None,
                )
                if sent_card is not None:
                    state.card_message_id = sent_card.message_id
                    state.card_is_photo = now_is_photo
                    if now_is_photo and rec is not None and getattr(sent_card, "photo", None):
                        self.media_resolver.record_telegram_file_id(
                            rec, sent_card.photo[-1].file_id
                        )
                    await self.manager.attach_message_reference(
                        match.match_id,
                        MessageReference(
                            chat_id=state.chat_id,
                            message_id=str(state.card_message_id),
                            kind="card",
                        ),
                    )
                    return

            edited_msg, state.card_is_photo = await edit_card_message_safe(
                self.bot,
                chat_id=state.chat_id,
                message_id=state.card_message_id,
                is_photo=state.card_is_photo,
                photo=photo,
                caption=caption,
                reply_markup=markup,
                fallback_photo=self.config.card_back_ref or None,
            )
            if state.card_is_photo and rec is not None and getattr(edited_msg, "photo", None):
                self.media_resolver.record_telegram_file_id(rec, edited_msg.photo[-1].file_id)

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
                photo = await self._character_media_photo_async(rec)
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
