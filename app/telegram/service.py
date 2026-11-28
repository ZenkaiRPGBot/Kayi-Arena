"""Application-to-Telegram UI coordinator for Kayi Arena (Module 6).

Connects Telegram commands and callbacks to MatchManager (Module 5),
CharacterDatabase (Module 4A), and Resolution (Module 3) while keeping
gameplay state strictly inside the application layer.
"""

from __future__ import annotations

import asyncio
import logging
import secrets
import time
from collections import deque
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Mapping, Sequence

from aiogram import Bot
from aiogram.types import BufferedInputFile, Message, User

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
from app.persistence.models import HistoricalMatchRecord, PlayerStatsSummary, StartupRecoveryReport
from app.telegram.config import BotConfig
from app.telegram.constants import ROLE_ORDER, UNIVERSES_PER_PAGE
from app.telegram.gameplay_logs import GameplayLogger
from app.telegram.media import CharacterMediaResolver
from app.telegram.profile_card import (
    PlayerCardCache,
    fetch_telegram_avatar_bytes,
    render_player_card_async,
)
from app.telegram.keyboards import (
    build_awaiting_shuffle_keyboard,
    build_challenge_keyboard,
    build_character_revealed_keyboard,
    build_detailed_results_keyboard,
    build_draft_board_keyboard,
    build_historical_breakdown_keyboard,
    build_historical_match_keyboard,
    build_inactivity_keyboard,
    build_match_results_keyboard,
    build_profile_card_keyboard,
    build_profile_history_keyboard,
    build_profile_stats_keyboard,
    build_profile_universe_keyboard,
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
    render_historical_battle_breakdown,
    render_historical_match_details,
    render_match_results,
    render_profile_history,
    render_profile_statistics,
    render_profile_text_fallback,
    render_profile_universe_selection,
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


@dataclass(slots=True)
class ProfileSession:
    """Tracks an isolated, revision-protected Player Profile 2.0 navigation session."""

    session_id: str
    requester_id: str
    owner_id: str
    chat_id: str
    message_id: int
    is_photo: bool
    revision: int = 1
    screen: str = "card"
    origin: str = "stats"
    mode: str = "ranked"
    universe_id: str = "all"
    history_page: int = 0
    univ_page: int = 0
    selected_match_id: str | None = None
    page_match_ids: tuple[str, ...] = ()
    closed: bool = False


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
        self.gameplay_logger = GameplayLogger(bot, channel_id=config.arena_log_channel_id)

        self._player_names: dict[str, str] = {}
        self._player_first_names: dict[str, str] = {}
        self._player_usernames: dict[str, str] = {}
        self._chat_titles: dict[str, str] = {}
        self._chat_usernames: dict[str, str] = {}
        self._universe_menus: dict[tuple[str, int], UniverseMenuContext] = {}
        self._challenge_messages: dict[str, tuple[str, int]] = {}
        self._match_ui: dict[str, MatchUIState] = {}
        self._forfeit_confirmations: dict[tuple[str, str], tuple[str, int, int]] = {}
        self._forfeit_locks: dict[tuple[str, str], asyncio.Lock] = {}
        self._terminal_rendered_matches: set[str] = set()
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
        self._profile_card_cache = PlayerCardCache(max_entries=64)
        self._profile_sessions: dict[str, ProfileSession] = {}
        self._profile_locks: dict[str, asyncio.Lock] = {}
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
                "batch": "all",
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

    def register_chat(
        self,
        chat_id: int | str,
        chat_type: str,
        title: str | None = None,
        username: str | None = None,
    ) -> None:
        cid = str(chat_id)
        if title:
            self._chat_titles[cid] = title
        if username:
            self._chat_usernames[cid] = username.lstrip("@")
        else:
            self._chat_usernames.pop(cid, None)
        if self.store is not None:
            self.store.upsert_known_chat(cid, chat_type, title)

    def chat_title(self, chat_id: str) -> str | None:
        return self._chat_titles.get(str(chat_id))

    def chat_username(self, chat_id: str) -> str | None:
        return self._chat_usernames.get(str(chat_id))

    # ------------------------------------------------------------------
    # Player & Metadata Helpers
    # ------------------------------------------------------------------

    def register_user(self, user: User | None) -> str:
        if user is None:
            return ""
        uid = str(user.id)
        first = (user.first_name or "").strip()
        if first:
            self._player_first_names[uid] = first
        name = (user.full_name or first or user.username or uid).strip()
        self._player_names[uid] = name
        if user.username:
            self._player_usernames[uid] = user.username
        if self.store is not None:
            self.store.upsert_player_profile(uid, name, user.username)
        return uid

    def first_name(self, player_id: str) -> str:
        first = self._player_first_names.get(player_id, "").strip()
        if first:
            return first
        full = self._player_names.get(player_id, "").strip()
        if full and full != str(player_id):
            return full.split()[0]
        return "Player"

    def display_name(self, player_id: str) -> str:
        return self._player_names.get(player_id, player_id)

    def player_names_for_match(self, match: ManagedMatch) -> dict[str, str]:
        return {pid: self.first_name(pid) for pid in match.players}

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
            challenger_name=self.first_name(challenge.challenger_id),
            target_name=(
                self.first_name(challenge.target_player_id)
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

    def cancel_challenge_expiry(self, challenge_id: str) -> None:
        self._cancel_timer(f"chl:{challenge_id}")

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

    def match_chat_id(self, match: ManagedMatch) -> str | None:
        state = self._match_ui.get(match.match_id)
        if state is not None:
            return state.chat_id
        for ref in reversed(match.message_refs):
            if ref.kind in {"board", "card", "game", "chat"}:
                return ref.chat_id
        return None

    def forfeit_lock(self, match_id: str, user_id: str) -> asyncio.Lock:
        key = (match_id, user_id)
        lock = self._forfeit_locks.get(key)
        if lock is None:
            lock = asyncio.Lock()
            self._forfeit_locks[key] = lock
        return lock

    async def _delete_or_strip_message(self, chat_id: str, message_id: int) -> None:
        try:
            await self.bot.delete_message(chat_id=chat_id, message_id=message_id)
            return
        except Exception:
            pass
        try:
            await self.bot.edit_message_reply_markup(
                chat_id=chat_id, message_id=message_id, reply_markup=None
            )
        except Exception:
            pass

    def get_forfeit_confirmation(
        self, match_id: str, user_id: str
    ) -> tuple[str, int, int] | None:
        return self._forfeit_confirmations.get((match_id, user_id))

    def register_forfeit_confirmation(
        self, match_id: str, user_id: str, chat_id: str, message_id: int, generation: int
    ) -> None:
        self._forfeit_confirmations[(match_id, user_id)] = (chat_id, message_id, generation)

    async def remove_forfeit_confirmation(self, match_id: str, user_id: str) -> None:
        info = self._forfeit_confirmations.pop((match_id, user_id), None)
        if info is not None:
            await self._delete_or_strip_message(info[0], info[1])

    async def cleanup_forfeit_confirmations(
        self, match_id: str, *, match: ManagedMatch | None = None
    ) -> None:
        keys = [k for k in self._forfeit_confirmations if k[0] == match_id]
        seen: set[tuple[str, int]] = set()
        for k in keys:
            info = self._forfeit_confirmations.pop(k, None)
            if info is not None:
                seen.add((info[0], info[1]))
                await self._delete_or_strip_message(info[0], info[1])
        if match is not None:
            for ref in match.message_refs:
                if ref.kind.startswith("fc:"):
                    try:
                        pair = (ref.chat_id, int(ref.message_id))
                    except ValueError:
                        continue
                    if pair not in seen:
                        seen.add(pair)
                        await self._delete_or_strip_message(pair[0], pair[1])

    async def _resolve_retained_photo(
        self, match: ManagedMatch
    ) -> tuple[CharacterEntry | None, Any | None]:
        ds = match.display_state
        if match.inactivity_claim_offered_to is None and match.draft_snapshot.held_character is not None:
            held = match.draft_snapshot.held_character
            rec = self.get_character_entry(held.character_id)
            photo = await self._character_media_photo_async(rec) if rec is not None else None
            if photo is None and ds.media_ref:
                photo = ds.media_ref
            return rec, photo

        fallback_id = ds.last_character_id or match.draft_snapshot.last_skipped_id
        if fallback_id:
            rec = self.get_character_entry(fallback_id)
            if ds.media_ref and ds.last_character_id:
                return rec, ds.media_ref
            photo = await self._character_media_photo_async(rec) if rec is not None else None
            return rec, photo
        return None, None

    async def _persist_card_media_state(
        self,
        match: ManagedMatch,
        *,
        rec: CharacterEntry | None,
        msg_obj: Any,
        is_photo: bool,
        fallback_photo: Any | None = None,
    ) -> None:
        media_ref: str | None = None
        if is_photo and getattr(msg_obj, "photo", None):
            fid = msg_obj.photo[-1].file_id
            media_ref = fid
            if rec is not None:
                self.media_resolver.record_telegram_file_id(rec, fid)
        elif is_photo and isinstance(fallback_photo, str) and fallback_photo:
            media_ref = fallback_photo
        await self.manager.update_display_state(
            match.match_id,
            media_ref=media_ref,
            card_is_photo=is_photo,
            last_character_name=rec.name if rec is not None else None,
        )

    async def start_match_ui(
        self,
        match: ManagedMatch,
        *,
        chat_id: str,
        reuse_challenge_message_id: int | None = None,
    ) -> MatchUIState | None:
        """Send (or reuse challenge message for) the two primary messages (board + text-only card)."""
        names = self.player_names_for_match(match)
        u_name = self.universe_name(match.universe_id)
        char_lookup = self.char_lookup_for_match(match)
        remaining = max(0.0, match.turn_deadline_at - self.manager.clock())
        board_text = render_draft_board(
            match,
            universe_name=u_name,
            player_names=names,
            char_lookup=char_lookup,
            seconds_remaining=remaining,
        )
        board_markup = build_draft_board_keyboard(match)

        board_chat_id = str(chat_id)
        board_msg_id: int | None = None
        if reuse_challenge_message_id is not None:
            reused = await edit_message_text_safe(
                self.bot,
                chat_id=chat_id,
                message_id=reuse_challenge_message_id,
                text=board_text,
                reply_markup=board_markup,
            )
            if reused:
                board_msg_id = reuse_challenge_message_id

        if board_msg_id is None:
            board_msg = await send_message_safe(
                self.bot,
                chat_id=chat_id,
                text=board_text,
                reply_markup=board_markup,
            )
            if board_msg is None:
                return None
            board_chat_id = str(board_msg.chat.id)
            board_msg_id = board_msg.message_id
            if reuse_challenge_message_id is not None:
                await self._delete_or_strip_message(board_chat_id, reuse_challenge_message_id)

        await self.manager.replace_message_references(
            match.match_id,
            (MessageReference(chat_id=board_chat_id, message_id=str(board_msg_id), kind="board"),),
            bump_generation=False,
        )

        card_text = render_awaiting_shuffle_card(
            match, player_names=names, seconds_remaining=remaining
        )
        card_msg = await send_message_safe(
            self.bot,
            chat_id=board_chat_id,
            text=card_text,
            reply_markup=build_awaiting_shuffle_keyboard(match),
        )
        if card_msg is None:
            await self._delete_or_strip_message(board_chat_id, board_msg_id)
            await self.manager.replace_message_references(
                match.match_id,
                (MessageReference(chat_id=board_chat_id, message_id="0", kind="chat"),),
                bump_generation=False,
            )
            return None

        state = MatchUIState(
            chat_id=board_chat_id,
            board_message_id=board_msg_id,
            card_message_id=card_msg.message_id,
            card_is_photo=False,
        )
        self._match_ui[match.match_id] = state
        await self.manager.replace_message_references(
            match.match_id,
            (
                MessageReference(chat_id=state.chat_id, message_id=str(state.board_message_id), kind="board"),
                MessageReference(chat_id=state.chat_id, message_id=str(state.card_message_id), kind="card"),
            ),
            bump_generation=False,
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
            state = self._restore_match_ui_from_refs(match)
        if state is None:
            return
        if last_action_line is not None:
            state.last_action_line = last_action_line

        names = self.player_names_for_match(match)
        u_name = self.universe_name(match.universe_id)

        if match.status is not MatchLifecycleStatus.DRAFTING:
            self._cancel_match_timers(match.match_id)
            self._recovery_locks.pop(match.match_id, None)
            for k in [k for k in self._forfeit_locks if k[0] == match.match_id]:
                self._forfeit_locks.pop(k, None)
            await self.cleanup_forfeit_confirmations(match.match_id, match=match)

            old_board_id = state.board_message_id
            old_card_id = state.card_message_id
            result_msg_id: int | None = None

            if update_board and match.match_id not in self._terminal_rendered_matches:
                char_lookup = self.char_lookup_for_match(match)
                result_text = render_match_results(
                    match,
                    universe_name=u_name,
                    player_names=names,
                    char_lookup=char_lookup,
                )
                result_markup = build_match_results_keyboard(match, player_names=names)
                sent_result = await send_message_safe(
                    self.bot,
                    chat_id=state.chat_id,
                    text=result_text,
                    reply_markup=result_markup,
                )
                if sent_result is not None:
                    self._terminal_rendered_matches.add(match.match_id)
                    result_msg_id = sent_result.message_id
                    state.board_message_id = result_msg_id
                    await self._delete_or_strip_message(state.chat_id, old_board_id)
                else:
                    edited_ok = await edit_message_text_safe(
                        self.bot,
                        chat_id=state.chat_id,
                        message_id=old_board_id,
                        text=result_text,
                        reply_markup=result_markup,
                    )
                    if edited_ok:
                        self._terminal_rendered_matches.add(match.match_id)
                        result_msg_id = old_board_id

            if update_card:
                try:
                    await self.bot.delete_message(
                        chat_id=state.chat_id, message_id=old_card_id
                    )
                except Exception:
                    retired_text = render_retired_card_text(match, player_names=names)
                    _, state.card_is_photo = await edit_card_message_safe(
                        self.bot,
                        chat_id=state.chat_id,
                        message_id=old_card_id,
                        is_photo=state.card_is_photo,
                        photo=None,
                        caption=retired_text,
                        reply_markup=None,
                    )

            for ref in match.message_refs:
                if ref.kind in {"board", "card", "game"}:
                    try:
                        rid = int(ref.message_id)
                    except ValueError:
                        continue
                    if ref.chat_id == state.chat_id and rid in {
                        old_board_id,
                        old_card_id,
                        result_msg_id,
                    }:
                        continue
                    await self._delete_or_strip_message(ref.chat_id, rid)

            try:
                await self.gameplay_logger.log_match_terminal(
                    match,
                    universe_name=u_name,
                    player_names=names,
                    char_lookup=self.char_lookup_for_match(match),
                    chat_id=state.chat_id,
                    group_title=self.chat_title(state.chat_id),
                    group_username=self.chat_username(state.chat_id),
                    group_link=self.build_group_link(state.chat_id),
                )
            except Exception:
                logger.warning("Failed logging terminal event for %s", match.match_id)
            return

        remaining = max(0.0, match.turn_deadline_at - self.manager.clock())

        if update_board:
            char_lookup = self.char_lookup_for_match(match)
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
                ),
                reply_markup=build_draft_board_keyboard(match),
            )

        if update_card:
            rec, photo = await self._resolve_retained_photo(match)
            if match.inactivity_claim_offered_to is not None:
                claim_rem = (
                    max(0.0, match.inactivity_claim_expires_at - self.manager.clock())
                    if match.inactivity_claim_expires_at is not None
                    else None
                )
                caption = render_turn_expired_card(
                    match, player_names=names, seconds_remaining=claim_rem
                )
                markup = build_inactivity_keyboard(match)
            elif match.draft_snapshot.phase is DraftPhase.AWAITING_SHUFFLE:
                caption = render_awaiting_shuffle_card(
                    match, player_names=names, seconds_remaining=remaining
                )
                markup = build_awaiting_shuffle_keyboard(match)
            else:
                held = match.draft_snapshot.held_character
                if rec is not None:
                    caption = render_revealed_character_card(
                        match,
                        character=rec,
                        universe_name=u_name,
                        player_names=names,
                        seconds_remaining=remaining,
                    )
                else:
                    cid = held.character_id if held else "Unknown"
                    caption = f"<b>{cid}</b>\n\nChoose a role."
                markup = build_character_revealed_keyboard(match)

            if not state.card_is_photo and photo is not None:
                sent_card, now_is_photo = await replace_text_with_photo_card_safe(
                    self.bot,
                    chat_id=state.chat_id,
                    old_message_id=state.card_message_id,
                    photo=photo,
                    caption=caption,
                    reply_markup=markup,
                )
                if sent_card is not None:
                    state.card_message_id = sent_card.message_id
                    state.card_is_photo = now_is_photo
                    await self._persist_card_media_state(
                        match, rec=rec, msg_obj=sent_card, is_photo=now_is_photo, fallback_photo=photo
                    )
                    await self.manager.replace_message_references(
                        match.match_id,
                        (
                            MessageReference(
                                chat_id=state.chat_id,
                                message_id=str(state.board_message_id),
                                kind="board",
                            ),
                            MessageReference(
                                chat_id=state.chat_id,
                                message_id=str(state.card_message_id),
                                kind="card",
                            ),
                        ),
                        bump_generation=False,
                    )
                    return

            edited_ok, state.card_is_photo = await edit_card_message_safe(
                self.bot,
                chat_id=state.chat_id,
                message_id=state.card_message_id,
                is_photo=state.card_is_photo,
                photo=photo,
                caption=caption,
                reply_markup=markup,
            )
            if edited_ok and state.card_is_photo:
                await self._persist_card_media_state(
                    match, rec=rec, msg_obj=None, is_photo=True, fallback_photo=photo
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
            card_is_photo=bool(match.display_state.card_is_photo),
        )
        self._match_ui[match.match_id] = state
        return state

    async def recover_game_ui(
        self, match: ManagedMatch, *, requester_id: str = ""
    ) -> MatchUIState | None:
        """Full-match recovery: invalidate old generation, remove/disable old UI, send fresh Board + Action Card."""
        async with self._recovery_lock(match.match_id):
            latest = self.manager.get_match(match.match_id) or match
            if latest.status is not MatchLifecycleStatus.DRAFTING:
                return None
            state = self._match_ui.get(latest.match_id) or self._restore_match_ui_from_refs(latest)
            target_chat_id = state.chat_id if state is not None else self.match_chat_id(latest)
            if not target_chat_id or target_chat_id.isdigit():
                return None

            names = self.player_names_for_match(latest)
            u_name = self.universe_name(latest.universe_id)
            char_lookup = self.char_lookup_for_match(latest)
            actor_id = requester_id or latest.players[0]

            # 1. Bump generation FIRST so obsolete controls cannot mutate the match
            refs_res = await self.manager.replace_message_references(
                latest.match_id, latest.message_refs, bump_generation=True
            )
            if not refs_res.accepted or refs_res.match is None:
                return None
            latest = self.manager.get_match(latest.match_id) or refs_res.match
            if latest.status is not MatchLifecycleStatus.DRAFTING:
                return None

            # 2. Remove or disable obsolete messages & temporary forfeit confirmations
            self._match_ui.pop(latest.match_id, None)
            await self.cleanup_forfeit_confirmations(latest.match_id, match=latest)
            if state is not None:
                await self._delete_or_strip_message(state.chat_id, state.board_message_id)
                await self._delete_or_strip_message(state.chat_id, state.card_message_id)
            for ref in latest.message_refs:
                if ref.kind in {"board", "card", "game"}:
                    try:
                        rid = int(ref.message_id)
                    except ValueError:
                        continue
                    if state is not None and ref.chat_id == state.chat_id and rid in {
                        state.board_message_id,
                        state.card_message_id,
                    }:
                        continue
                    await self._delete_or_strip_message(ref.chat_id, rid)

            # Invalidate stale board/card refs while retaining group chat_id for retries
            try:
                await self.manager.replace_message_references(
                    latest.match_id,
                    (MessageReference(chat_id=target_chat_id, message_id="0", kind="chat"),),
                    bump_generation=False,
                )
            except Exception:
                pass

            # Reconcile latest durable state & deadline right before sending controls
            latest = self.manager.get_match(latest.match_id) or latest
            if latest.status is not MatchLifecycleStatus.DRAFTING:
                return None
            remaining = max(0.0, latest.turn_deadline_at - self.manager.clock())

            board_text = render_draft_board(
                latest,
                universe_name=u_name,
                player_names=names,
                char_lookup=char_lookup,
                seconds_remaining=remaining,
            )
            board_markup = build_draft_board_keyboard(latest)

            rec, photo = await self._resolve_retained_photo(latest)
            if latest.inactivity_claim_offered_to is not None:
                claim_rem = (
                    max(0.0, latest.inactivity_claim_expires_at - self.manager.clock())
                    if latest.inactivity_claim_expires_at is not None
                    else None
                )
                caption = render_turn_expired_card(
                    latest, player_names=names, seconds_remaining=claim_rem
                )
                markup = build_inactivity_keyboard(latest)
            elif latest.draft_snapshot.phase is DraftPhase.AWAITING_SHUFFLE:
                caption = render_awaiting_shuffle_card(
                    latest, player_names=names, seconds_remaining=remaining
                )
                markup = build_awaiting_shuffle_keyboard(latest)
            else:
                held = latest.draft_snapshot.held_character
                caption = (
                    render_revealed_character_card(
                        latest,
                        character=rec,
                        universe_name=u_name,
                        player_names=names,
                        seconds_remaining=remaining,
                    )
                    if rec is not None
                    else f"<b>{held.character_id if held else 'Character'}</b>\n\nChoose a role."
                )
                markup = build_character_revealed_keyboard(latest)

            # 3. Send fresh Draft Board in original group
            new_board = await send_message_safe(
                self.bot,
                chat_id=target_chat_id,
                text=board_text,
                reply_markup=board_markup,
            )
            if new_board is None:
                try:
                    await self.gameplay_logger.log_recovery(
                        latest,
                        succeeded=False,
                        requester_id=actor_id,
                        player_names=names,
                        chat_id=target_chat_id,
                        group_title=self.chat_title(target_chat_id),
                        group_link=self.build_group_link(target_chat_id),
                        stage="Draft Board restoration",
                        detail="Telegram API request failed.",
                    )
                except Exception:
                    pass
                return None

            # 4. Send fresh Action Card immediately afterward
            if photo is not None:
                new_card, is_photo = await send_photo_or_text_safe(
                    self.bot,
                    chat_id=target_chat_id,
                    photo=photo,
                    caption=caption,
                    reply_markup=markup,
                )
            else:
                new_card = await send_message_safe(
                    self.bot,
                    chat_id=target_chat_id,
                    text=caption,
                    reply_markup=markup,
                )
                is_photo = False

            if new_card is None:
                await self._delete_or_strip_message(target_chat_id, new_board.message_id)
                try:
                    await self.gameplay_logger.log_recovery(
                        latest,
                        succeeded=False,
                        requester_id=actor_id,
                        player_names=names,
                        chat_id=target_chat_id,
                        group_title=self.chat_title(target_chat_id),
                        group_link=self.build_group_link(target_chat_id),
                        stage="Action Card restoration",
                        detail="Telegram API request failed.",
                    )
                except Exception:
                    pass
                return None

            # 5. Persist both new message IDs before reporting success
            try:
                persist_res = await self.manager.replace_message_references(
                    latest.match_id,
                    (
                        MessageReference(
                            chat_id=target_chat_id,
                            message_id=str(new_board.message_id),
                            kind="board",
                        ),
                        MessageReference(
                            chat_id=target_chat_id,
                            message_id=str(new_card.message_id),
                            kind="card",
                        ),
                    ),
                    bump_generation=False,
                )
            except Exception:
                persist_res = None
            if persist_res is None or not persist_res.accepted:
                await self._delete_or_strip_message(target_chat_id, new_board.message_id)
                await self._delete_or_strip_message(target_chat_id, new_card.message_id)
                try:
                    await self.gameplay_logger.log_recovery(
                        latest,
                        succeeded=False,
                        requester_id=actor_id,
                        player_names=names,
                        chat_id=target_chat_id,
                        group_title=self.chat_title(target_chat_id),
                        group_link=self.build_group_link(target_chat_id),
                        stage="Persistence commit",
                        detail="Failed persisting replacement message IDs.",
                    )
                except Exception:
                    pass
                return None

            new_state = MatchUIState(
                chat_id=target_chat_id,
                board_message_id=new_board.message_id,
                card_message_id=new_card.message_id,
                card_is_photo=is_photo,
            )
            self._match_ui[latest.match_id] = new_state
            await self._persist_card_media_state(
                latest, rec=rec, msg_obj=new_card, is_photo=is_photo, fallback_photo=photo
            )

            # Re-arm claim or turn timer with the new generation
            post = self.manager.get_match(latest.match_id) or latest
            if post.status is not MatchLifecycleStatus.DRAFTING or (
                post.draft_snapshot.revision != latest.draft_snapshot.revision
                or post.inactivity_claim_offered_to != latest.inactivity_claim_offered_to
            ):
                await self.sync_match_ui(post, update_board=True, update_card=True)
            if post.status is MatchLifecycleStatus.DRAFTING:
                if post.inactivity_claim_offered_to is not None:
                    self.schedule_claim_window_timeout(post)
                else:
                    self.schedule_turn_timeout(post)

            try:
                await self.gameplay_logger.log_recovery(
                    latest,
                    succeeded=True,
                    requester_id=actor_id,
                    player_names=names,
                    chat_id=target_chat_id,
                    group_title=self.chat_title(target_chat_id),
                    group_link=self.build_group_link(target_chat_id),
                )
            except Exception:
                pass
            return new_state

    def build_game_link(self, match: ManagedMatch) -> str | None:
        state = self._match_ui.get(match.match_id) or self._restore_match_ui_from_refs(match)
        if state is None:
            return None
        try:
            cid = int(state.chat_id)
        except ValueError:
            return None
        # Telegram c/<internal_id>/<msg_id> links work for supergroups/channels (-100...)
        if cid < -1000000000000 and state.card_message_id:
            internal = str(abs(cid) - 1000000000000)
            return f"https://t.me/c/{internal}/{state.card_message_id}"
        return None

    def build_group_link(self, chat_id: str) -> str | None:
        uname = self.chat_username(chat_id)
        if uname:
            return f"https://t.me/{uname}"
        try:
            cid = int(chat_id)
        except ValueError:
            return None
        if cid < -1000000000000:
            internal = str(abs(cid) - 1000000000000)
            return f"https://t.me/c/{internal}"
        return None

    # ------------------------------------------------------------------
    # Shared Result Battle Breakdown Navigation (Screen 11)
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
        await edit_message_text_safe(
            self.bot,
            chat_id=chat_id,
            message_id=source_message_id,
            text=text,
            reply_markup=markup,
        )

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

    # ------------------------------------------------------------------
    # Player Profile 2.0 (Card, Stats, Universe Filter, History, Details)
    # ------------------------------------------------------------------

    def get_profile_session(self, session_id: str) -> ProfileSession | None:
        return self._profile_sessions.get(session_id)

    def _profile_lock(self, session_id: str) -> asyncio.Lock:
        lock = self._profile_locks.get(session_id)
        if lock is None:
            lock = asyncio.Lock()
            self._profile_locks[session_id] = lock
        return lock

    def _save_profile_session(self, session: ProfileSession) -> None:
        if len(self._profile_sessions) >= 500:
            oldest = next(iter(self._profile_sessions))
            self._profile_sessions.pop(oldest, None)
            self._profile_locks.pop(oldest, None)
        self._profile_sessions[session.session_id] = session

    def resolve_player_names(self, player_ids: Sequence[str]) -> dict[str, str]:
        result: dict[str, str] = {}
        missing: list[str] = []
        for pid in player_ids:
            if not pid:
                continue
            first = self._player_first_names.get(pid, "").strip()
            if first:
                result[pid] = first
                continue
            full = self._player_names.get(pid, "").strip()
            if full and full != str(pid):
                result[pid] = full.split()[0]
                continue
            missing.append(pid)
        if missing and self.store is not None and hasattr(self.store, "get_player_display_names"):
            stored = self.store.get_player_display_names(missing)
            for pid, disp in stored.items():
                clean = (disp or "").strip()
                if clean and clean != str(pid):
                    result[pid] = clean.split()[0]
        for pid in player_ids:
            if pid and pid not in result:
                result[pid] = "Player"
        return result

    def profile_universes(self, owner_id: str) -> tuple[Any, ...]:
        from types import SimpleNamespace

        by_id: dict[str, Any] = {u.universe_id: u for u in self.eligible_universes()}
        if self.store is not None and hasattr(self.store, "list_player_history_universes"):
            for uid in self.store.list_player_history_universes(owner_id):
                if uid and uid not in by_id:
                    try:
                        by_id[uid] = self.db.get_universe(uid)
                    except Exception:
                        by_id[uid] = SimpleNamespace(
                            universe_id=uid,
                            name=uid.replace("_", " ").title(),
                        )
        items = list(by_id.values())
        items.sort(key=lambda u: (u.name.lower(), u.universe_id))
        return tuple(items)

    def _universe_label_for_profile(self, universe_id: str) -> str:
        if universe_id == "all":
            return "All Universes"
        return self.universe_name(universe_id)

    def _compute_profile_stats(
        self, owner_id: str, *, game_mode: str = "ranked", universe_id: str = "all"
    ) -> PlayerStatsSummary:
        if self.store is not None and hasattr(self.store, "compute_player_statistics"):
            return self.store.compute_player_statistics(
                owner_id,
                game_mode=game_mode,
                universe_id=None if universe_id == "all" else universe_id,
            )
        return PlayerStatsSummary()

    def _history_char_lookup(self, rec: HistoricalMatchRecord) -> dict[str, CharacterEntry]:
        lookup: dict[str, CharacterEntry] = {}
        res = rec.outcome.resolution
        if res is None:
            return lookup
        for m in res.matchups:
            for cid in (m.player_1.character_id, m.player_2.character_id):
                if cid and cid not in lookup:
                    entry = self.get_character_entry(cid)
                    if entry is not None:
                        lookup[cid] = entry
        return lookup

    async def _send_profile_card_message(
        self,
        *,
        chat_id: str | int,
        owner_id: str,
        session_id: str,
        revision: int,
    ) -> tuple[Message | None, bool]:
        stats = self._compute_profile_stats(owner_id, game_mode="ranked", universe_id="all")
        owner_name = self.resolve_player_names([owner_id]).get(owner_id, "Player")
        markup = build_profile_card_keyboard(session_id=session_id, revision=revision)

        try:
            avatar_bytes = await fetch_telegram_avatar_bytes(self.bot, owner_id, timeout=3.0)
            key, cached = await render_player_card_async(
                cache=self._profile_card_cache,
                player_id=owner_id,
                name=owner_name,
                wins=stats.victories,
                losses=stats.defeats,
                draws=stats.draws,
                avatar_bytes=avatar_bytes,
            )
            media = (
                cached.telegram_file_id
                if cached.telegram_file_id
                else BufferedInputFile(cached.png_bytes, filename="profile_card.png")
            )
            sent, is_photo = await send_photo_or_text_safe(
                self.bot,
                chat_id=chat_id,
                photo=media,
                caption="",
                reply_markup=markup,
            )
            if sent is not None and is_photo and getattr(sent, "photo", None):
                self._profile_card_cache.set_file_id(key, sent.photo[-1].file_id)
            if sent is not None and is_photo:
                return sent, True
        except Exception as exc:
            logger.warning("Profile card render failed for %s: %s", owner_id, type(exc).__name__)

        fallback_text = render_profile_text_fallback(
            player_id=owner_id, player_name=owner_name, stats=stats
        )
        sent_fb = await send_message_safe(
            self.bot,
            chat_id=chat_id,
            text=fallback_text,
            reply_markup=markup,
        )
        return sent_fb, False

    def _build_profile_text_screen(
        self,
        session: ProfileSession,
        *,
        screen: str,
        revision: int,
    ) -> tuple[str, Any, tuple[str, ...]]:
        owner_id = session.owner_id
        owner_name = self.resolve_player_names([owner_id]).get(owner_id, "Player")
        u_label = self._universe_label_for_profile(session.universe_id)

        if screen == "stats":
            stats = self._compute_profile_stats(
                owner_id, game_mode=session.mode, universe_id=session.universe_id
            )
            text = render_profile_statistics(
                player_id=owner_id,
                player_name=owner_name,
                universe_label=u_label,
                game_mode=session.mode,
                stats=stats,
            )
            markup = build_profile_stats_keyboard(
                session_id=session.session_id,
                revision=revision,
                game_mode=session.mode,
                universe_id=session.universe_id,
                universe_label=u_label,
            )
            return text, markup, session.page_match_ids

        if screen == "univ":
            universes = self.profile_universes(owner_id)
            total_pages = max(1, (len(universes) + UNIVERSES_PER_PAGE - 1) // UNIVERSES_PER_PAGE)
            session.univ_page = max(0, min(session.univ_page, total_pages - 1))
            text = render_profile_universe_selection(
                player_id=owner_id,
                player_name=owner_name,
                selected_label=u_label,
                game_mode=session.mode,
                origin=session.origin,
            )
            markup = build_profile_universe_keyboard(
                session_id=session.session_id,
                revision=revision,
                universes=universes,
                selected_universe_id=session.universe_id,
                page=session.univ_page,
            )
            return text, markup, session.page_match_ids

        if screen == "history":
            per_page = 5
            records: list[HistoricalMatchRecord] = []
            total_count = 0
            if self.store is not None and hasattr(self.store, "query_player_history"):
                _, total_count = self.store.query_player_history(
                    owner_id,
                    game_mode=session.mode,
                    universe_id=None if session.universe_id == "all" else session.universe_id,
                    limit=1,
                    offset=0,
                )
            total_pages = max(1, (total_count + per_page - 1) // per_page)
            session.history_page = max(0, min(session.history_page, total_pages - 1))
            if total_count > 0 and self.store is not None:
                records, _ = self.store.query_player_history(
                    owner_id,
                    game_mode=session.mode,
                    universe_id=None if session.universe_id == "all" else session.universe_id,
                    limit=per_page,
                    offset=session.history_page * per_page,
                )
            opp_ids = [
                r.player_2_id if r.player_1_id == owner_id else r.player_1_id for r in records
            ]
            names = self.resolve_player_names([owner_id, *opp_ids])
            text = render_profile_history(
                player_id=owner_id,
                player_name=owner_name,
                universe_id=session.universe_id,
                universe_label=u_label,
                game_mode=session.mode,
                records=records,
                player_names=names,
            )
            markup = build_profile_history_keyboard(
                session_id=session.session_id,
                revision=revision,
                owner_id=owner_id,
                records=records,
                page=session.history_page,
                total_pages=total_pages,
                game_mode=session.mode,
                universe_id=session.universe_id,
                universe_label=u_label,
            )
            return text, markup, tuple(r.match_id for r in records)

        if screen in {"detail", "breakdown"}:
            rec = (
                self.store.get_historical_match(session.selected_match_id)
                if (self.store is not None and session.selected_match_id)
                else None
            )
            if rec is None:
                text = "<b>Battle Record Unavailable</b>\n\nThis match record could not be loaded."
                markup = build_historical_match_keyboard(
                    session_id=session.session_id, revision=revision, has_breakdown=False
                )
                return text, markup, session.page_match_ids

            names = self.resolve_player_names([rec.player_1_id, rec.player_2_id])
            chars = self._history_char_lookup(rec)
            if screen == "detail":
                dur = (
                    self.store.get_match_duration_seconds(rec.match_id)
                    if (self.store is not None and hasattr(self.store, "get_match_duration_seconds"))
                    else None
                )
                text = render_historical_match_details(
                    rec,
                    universe_name=self.universe_name(rec.universe_id),
                    player_names=names,
                    char_lookup=chars,
                    duration_seconds=dur,
                )
                markup = build_historical_match_keyboard(
                    session_id=session.session_id,
                    revision=revision,
                    has_breakdown=(rec.outcome.resolution is not None),
                )
            else:
                text = render_historical_battle_breakdown(
                    rec, player_names=names, char_lookup=chars
                )
                markup = build_historical_breakdown_keyboard(
                    session_id=session.session_id, revision=revision
                )
            return text, markup, session.page_match_ids

        # Fallback text card
        stats = self._compute_profile_stats(owner_id, game_mode="ranked", universe_id="all")
        return (
            render_profile_text_fallback(player_id=owner_id, player_name=owner_name, stats=stats),
            build_profile_card_keyboard(session_id=session.session_id, revision=revision),
            session.page_match_ids,
        )

    async def open_profile_session(
        self,
        *,
        chat_id: int | str,
        requester_id: str,
        owner_id: str,
        start_screen: str = "card",
    ) -> ProfileSession | None:
        sid = secrets.token_hex(4)
        session = ProfileSession(
            session_id=sid,
            requester_id=requester_id,
            owner_id=owner_id,
            chat_id=str(chat_id),
            message_id=0,
            is_photo=(start_screen == "card"),
            revision=1,
            screen=start_screen,
        )
        if start_screen == "card":
            sent, is_photo = await self._send_profile_card_message(
                chat_id=chat_id, owner_id=owner_id, session_id=sid, revision=1
            )
            if sent is None:
                return None
            session.message_id = sent.message_id
            session.is_photo = is_photo
            session.chat_id = str(sent.chat.id)
        else:
            text, markup, page_ids = self._build_profile_text_screen(
                session, screen="history", revision=1
            )
            sent = await send_message_safe(
                self.bot, chat_id=chat_id, text=text, reply_markup=markup
            )
            if sent is None:
                return None
            session.message_id = sent.message_id
            session.is_photo = False
            session.chat_id = str(sent.chat.id)
            session.page_match_ids = page_ids

        self._save_profile_session(session)
        return session

    async def handle_profile_action(
        self,
        *,
        session: ProfileSession,
        subaction: str,
        arg: str,
        chat_id: str,
        msg_id: int,
        expected_revision: int | None = None,
    ) -> tuple[bool, str | None]:
        async with self._profile_lock(session.session_id):
            if session.closed:
                return False, "This profile view has been closed."
            if (
                chat_id != session.chat_id
                or msg_id != session.message_id
                or (expected_revision is not None and expected_revision != session.revision)
            ):
                return False, "This profile interface is outdated. Use /profile or /history to open a fresh view."

            if subaction == "cl":
                session.closed = True
                session.revision += 1
                await self._delete_or_strip_message(chat_id, msg_id)
                return True, None

            target_screen = session.screen
            if subaction == "st":
                target_screen = "stats"
            elif subaction == "hs":
                target_screen = "history"
                session.history_page = 0
            elif subaction == "md":
                session.mode = "friendly" if arg == "f" else "ranked"
                if session.screen == "history":
                    session.history_page = 0
                target_screen = session.screen
            elif subaction == "uv":
                session.origin = session.screen if session.screen in {"stats", "history"} else "stats"
                session.univ_page = 0
                target_screen = "univ"
            elif subaction == "us":
                if arg.startswith("#"):
                    try:
                        uidx = int(arg[1:])
                    except ValueError:
                        return False, "Invalid universe selection."
                    universes = self.profile_universes(session.owner_id)
                    if uidx < 0 or uidx >= len(universes):
                        return False, "This universe selection is no longer available."
                    session.universe_id = universes[uidx].universe_id
                else:
                    session.universe_id = arg or "all"
                if session.origin == "history":
                    session.history_page = 0
                target_screen = session.origin
            elif subaction == "up":
                try:
                    session.univ_page = max(0, int(arg))
                except ValueError:
                    return False, "Invalid page."
                target_screen = "univ"
            elif subaction == "hp":
                try:
                    session.history_page = max(0, int(arg))
                except ValueError:
                    return False, "Invalid page."
                target_screen = "history"
            elif subaction == "hm":
                try:
                    idx = int(arg)
                except ValueError:
                    return False, "Invalid match selection."
                if idx < 0 or idx >= len(session.page_match_ids):
                    return False, "This match selection is no longer available."
                session.selected_match_id = session.page_match_ids[idx]
                target_screen = "detail"
            elif subaction == "bd":
                if not session.selected_match_id:
                    return False, "Match details are unavailable."
                target_screen = "breakdown"
            elif subaction == "bk":
                if session.screen == "breakdown":
                    target_screen = "detail"
                elif session.screen == "detail":
                    target_screen = "history"
                elif session.screen == "univ":
                    target_screen = session.origin
                elif session.screen in {"stats", "history"}:
                    target_screen = "card"
                else:
                    return False, None
            else:
                return False, "Unknown profile action."

            next_rev = session.revision + 1
            if target_screen == "card":
                if not session.is_photo:
                    sent, is_photo = await self._send_profile_card_message(
                        chat_id=chat_id,
                        owner_id=session.owner_id,
                        session_id=session.session_id,
                        revision=next_rev,
                    )
                    if sent is None:
                        return False, "Could not restore Player Card. Please try again."
                    old_msg_id = session.message_id
                    session.message_id = sent.message_id
                    session.is_photo = is_photo
                    session.screen = "card"
                    session.revision = next_rev
                    await self._delete_or_strip_message(chat_id, old_msg_id)
                return True, None

            text, markup, page_ids = self._build_profile_text_screen(
                session, screen=target_screen, revision=next_rev
            )
            if session.is_photo:
                sent = await send_message_safe(
                    self.bot, chat_id=chat_id, text=text, reply_markup=markup
                )
                if sent is None:
                    return False, "Could not open view. Please try again."
                old_msg_id = session.message_id
                session.message_id = sent.message_id
                session.is_photo = False
                session.screen = target_screen
                session.page_match_ids = page_ids
                session.revision = next_rev
                await self._delete_or_strip_message(chat_id, old_msg_id)
                return True, None

            edited = await edit_message_text_safe(
                self.bot,
                chat_id=chat_id,
                message_id=session.message_id,
                text=text,
                reply_markup=markup,
            )
            if not edited:
                return False, "Could not update view. Please try again."
            session.screen = target_screen
            session.page_match_ids = page_ids
            session.revision = next_rev
            return True, None
