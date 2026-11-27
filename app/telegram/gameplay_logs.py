"""Dedicated Kayi Arena Gameplay Logs (Part VII — ARENA_LOG_CHANNEL_ID).

Sends structured, non-blocking HTML match logs to a dedicated private Telegram
channel without exposing secrets, blocking gameplay, or polluting restart logs.
"""

from __future__ import annotations

import asyncio
import html
import logging
from collections import deque
from datetime import datetime, timedelta, timezone
from typing import Callable, Mapping

from aiogram import Bot
from aiogram.enums import ParseMode
from aiogram.exceptions import (
    TelegramBadRequest,
    TelegramForbiddenError,
    TelegramNetworkError,
    TelegramRetryAfter,
)

from app.database import CharacterEntry
from app.matches import ManagedMatch, MatchOutcomeReason
from app.resolution import MatchupWinner
from app.telegram.constants import (
    MAX_MESSAGE_LENGTH,
    ROLE_ORDER,
    SECTION_SEPARATOR,
    STATUS_DEFEAT,
    STATUS_DRAW,
    STATUS_NO_RESPONSE,
    STATUS_TIMEOUT,
    STATUS_VICTORY,
    to_bold_serif_upper,
)

logger = logging.getLogger(__name__)

IST = timezone(timedelta(hours=5, minutes=30))


def _esc(value: object) -> str:
    return html.escape(str(value or ""), quote=True)


def _mention(user_id: str, first_name: str | None) -> str:
    uid_str = str(user_id).strip()
    label = (first_name or "").strip()
    if not label or label == uid_str:
        label = "Player"
    safe = _esc(label)
    if uid_str.isdigit():
        return f'<a href="tg://user?id={uid_str}">{safe}</a>'
    return safe


def _format_duration_hms(seconds: float) -> str:
    secs = max(0, int(round(seconds)))
    hours, rem = divmod(secs, 3600)
    mins, s = divmod(rem, 60)
    if hours > 0:
        return f"{hours}h {mins}m {s}s"
    if mins > 0:
        return f"{mins}m {s}s"
    return f"{s}s"


def _clamp(text: str, limit: int = MAX_MESSAGE_LENGTH) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


class GameplayLogger:
    """Non-blocking, deduplicated logger for ARENA_LOG_CHANNEL_ID."""

    def __init__(
        self,
        bot: Bot,
        *,
        channel_id: int = 0,
        clock: Callable[[], datetime] | None = None,
        max_attempts: int = 3,
        max_dedup_keys: int = 2048,
    ) -> None:
        self.bot = bot
        self.channel_id = int(channel_id or 0)
        self.clock = clock or (lambda: datetime.now(IST))
        self.max_attempts = max(1, int(max_attempts))
        self._sent_keys: deque[str] = deque(maxlen=max_dedup_keys)
        self._sent_set: set[str] = set()
        self._lock = asyncio.Lock()

    @property
    def enabled(self) -> bool:
        return self.channel_id != 0

    def _mark_if_new(self, dedup_key: str) -> bool:
        if dedup_key in self._sent_set:
            return False
        if len(self._sent_keys) == self._sent_keys.maxlen:
            oldest = self._sent_keys.popleft()
            self._sent_set.discard(oldest)
        self._sent_keys.append(dedup_key)
        self._sent_set.add(dedup_key)
        return True

    async def _send_text(self, text: str, *, dedup_key: str | None = None) -> bool:
        if not self.enabled:
            return False
        if dedup_key is not None:
            async with self._lock:
                if not self._mark_if_new(dedup_key):
                    return False

        payload = _clamp(text)
        for attempt in range(self.max_attempts):
            try:
                await self.bot.send_message(
                    chat_id=self.channel_id,
                    text=payload,
                    parse_mode=ParseMode.HTML,
                    disable_web_page_preview=True,
                )
                return True
            except TelegramRetryAfter as exc:
                wait = min(float(getattr(exc, "retry_after", 1.0)), 5.0)
                if attempt + 1 >= self.max_attempts:
                    logger.warning("Gameplay log rate-limited; giving up")
                    return False
                await asyncio.sleep(wait)
            except TelegramForbiddenError:
                logger.warning("Gameplay log channel %s inaccessible (forbidden)", self.channel_id)
                return False
            except TelegramBadRequest as exc:
                logger.warning("Gameplay log BadRequest: %s", exc)
                return False
            except TelegramNetworkError as exc:
                if attempt + 1 >= self.max_attempts:
                    logger.warning("Gameplay log network error: %s", type(exc).__name__)
                    return False
                await asyncio.sleep(0.5 * (attempt + 1))
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning("Unexpected gameplay log error: %s", type(exc).__name__)
                return False
        return False

    def _timestamp_str(self) -> str:
        return self.clock().astimezone(IST).strftime("%Y-%m-%d %I:%M:%S %p IST")

    @staticmethod
    def _group_lines(
        *,
        chat_id: str,
        group_title: str | None,
        group_username: str | None,
        group_link: str | None = None,
    ) -> list[str]:
        title_str = _esc(group_title) if group_title else "Unknown Group"
        if group_link:
            title_str = f'<a href="{_esc(group_link)}">{title_str}</a>'
        username_str = f"@{_esc(group_username.lstrip('@'))}" if group_username else "Not available"
        return [
            f"<b>{to_bold_serif_upper('GROUP INFO')}</b>",
            "",
            f"▪ <b>Group:</b> {title_str}",
            f"▪ <b>Group ID:</b> <code>{_esc(chat_id)}</code>",
            f"▪ <b>Username:</b> {username_str}",
        ]

    async def log_match_started(
        self,
        match: ManagedMatch,
        *,
        universe_name: str,
        player_names: Mapping[str, str],
        player_usernames: Mapping[str, str] | None = None,
        chat_id: str,
        group_title: str | None = None,
        group_username: str | None = None,
        group_link: str | None = None,
    ) -> bool:
        p1_id, p2_id = match.players
        p1_m = _mention(p1_id, player_names.get(p1_id))
        p2_m = _mention(p2_id, player_names.get(p2_id))
        mode_str = "Ranked" if match.game_mode == "ranked" else "Friendly"
        starter_id = match.draft_snapshot.starting_player_id or p1_id
        starter_m = _mention(starter_id, player_names.get(starter_id))

        lines = [
            f"<b>📋 {to_bold_serif_upper('MATCH LOG')}</b> · #MATCH_STARTED",
            "",
            f"◆ <b>Match ID:</b> <code>{_esc(match.match_id)}</code>",
            f"◆ <b>Challenge ID:</b> <code>{_esc(match.challenge_id)}</code>",
            f"◆ <b>Universe:</b> {_esc(universe_name)}",
            f"◆ <b>Mode:</b> {mode_str}",
            f"◆ <b>Dataset:</b> <code>{_esc(match.dataset_version)}</code>",
            "",
            SECTION_SEPARATOR,
            "",
            *self._group_lines(
                chat_id=chat_id,
                group_title=group_title,
                group_username=group_username,
                group_link=group_link,
            ),
            "",
            f"<b>{to_bold_serif_upper('PLAYERS')}</b>",
            "",
            f"🔵 {p1_m} · <b>User ID:</b> <code>{_esc(p1_id)}</code>",
            f"🔴 {p2_m} · <b>User ID:</b> <code>{_esc(p2_id)}</code>",
            f"▪ <b>Starting Player:</b> {starter_m}",
            "",
            f"<i>{_esc(self._timestamp_str())}</i>",
        ]
        return await self._send_text(
            "\n".join(lines),
            dedup_key=f"MATCH_STARTED:{match.match_id}",
        )

    async def log_match_terminal(
        self,
        match: ManagedMatch,
        *,
        universe_name: str,
        player_names: Mapping[str, str],
        char_lookup: Mapping[str, CharacterEntry],
        chat_id: str,
        group_title: str | None = None,
        group_username: str | None = None,
        group_link: str | None = None,
    ) -> bool:
        outcome = match.outcome
        if outcome is None:
            return False

        if outcome.reason in {
            MatchOutcomeReason.NORMAL_MATCHUP_COUNT,
            MatchOutcomeReason.NORMAL_COMBINED_SCORE,
            MatchOutcomeReason.NORMAL_DRAW,
        }:
            tag = "#COMPLETED"
        elif outcome.reason is MatchOutcomeReason.VOLUNTARY_FORFEITURE:
            tag = "#FORFEITED"
        elif outcome.reason is MatchOutcomeReason.INACTIVITY_VICTORY:
            tag = "#INACTIVITY"
        elif outcome.reason is MatchOutcomeReason.MUTUAL_INACTIVITY_ABANDONMENT:
            tag = "#ABANDONED"
        else:
            tag = "#ERROR"

        p1_id, p2_id = match.players
        p1_m = _mention(p1_id, player_names.get(p1_id))
        p2_m = _mention(p2_id, player_names.get(p2_id))
        mode_str = "Ranked" if match.game_mode == "ranked" else "Friendly"
        duration_str = _format_duration_hms(max(0.0, match.updated_at - match.created_at))

        p1_skips_used = max(0, 2 - match.public_view.skips_remaining.get(p1_id, 2))
        p2_skips_used = max(0, 2 - match.public_view.skips_remaining.get(p2_id, 2))
        p1_ext_used = max(
            0, match.timeout_policy.extensions_per_player - match.extensions_remaining.get(p1_id, 0)
        )
        p2_ext_used = max(
            0, match.timeout_policy.extensions_per_player - match.extensions_remaining.get(p2_id, 0)
        )

        if tag == "#ABANDONED":
            timed_out_id = outcome.inactive_player_id or match.draft_snapshot.active_player_id or p1_id
            p1_status = STATUS_TIMEOUT if timed_out_id == p1_id else STATUS_NO_RESPONSE
            p2_status = STATUS_TIMEOUT if timed_out_id == p2_id else STATUS_NO_RESPONSE
        elif outcome.winner_id == p1_id:
            p1_status, p2_status = STATUS_VICTORY, STATUS_DEFEAT
        elif outcome.winner_id == p2_id:
            p1_status, p2_status = STATUS_DEFEAT, STATUS_VICTORY
        else:
            p1_status = p2_status = STATUS_DRAW

        lines = [
            f"<b>📋 {to_bold_serif_upper('MATCH LOG')}</b> · {tag}",
            "",
            f"◆ <b>Match ID:</b> <code>{_esc(match.match_id)}</code>",
            f"◆ <b>Challenge ID:</b> <code>{_esc(match.challenge_id)}</code>",
            f"◆ <b>Universe:</b> {_esc(universe_name)}",
            f"◆ <b>Mode:</b> {mode_str}",
            f"◆ <b>Dataset:</b> <code>{_esc(match.dataset_version)}</code>",
            "",
            SECTION_SEPARATOR,
            "",
            *self._group_lines(
                chat_id=chat_id,
                group_title=group_title,
                group_username=group_username,
                group_link=group_link,
            ),
            "",
            f"<b>{to_bold_serif_upper('PLAYERS')}</b>",
            "",
        ]

        res = outcome.resolution
        p1_lines = [
            f"🔵 {p1_m} 〔{p1_status}〕",
            f"▪ <b>User ID:</b> <code>{_esc(p1_id)}</code>",
        ]
        p2_lines = [
            f"🔴 {p2_m} 〔{p2_status}〕",
            f"▪ <b>User ID:</b> <code>{_esc(p2_id)}</code>",
        ]
        if res is not None:
            p1_lines.append(f"▪ <b>Team score:</b> {res.summary.total_player_1}/700")
            p2_lines.append(f"▪ <b>Team score:</b> {res.summary.total_player_2}/700")
        p1_lines.append(f"▪ <b>Skips used:</b> {p1_skips_used}/2 · <b>Extensions:</b> {p1_ext_used}")
        p2_lines.append(f"▪ <b>Skips used:</b> {p2_skips_used}/2 · <b>Extensions:</b> {p2_ext_used}")
        lines.extend(p1_lines + [""] + p2_lines)

        lines.extend(["", SECTION_SEPARATOR, "", f"<b>{to_bold_serif_upper('ROLE ASSIGNMENTS')}</b>", ""])
        if res is not None:
            for m in res.matchups:
                c1 = char_lookup.get(m.player_1.character_id)
                c2 = char_lookup.get(m.player_2.character_id)
                c1_name = c1.name if c1 is not None else m.player_1.character_id
                c2_name = c2.name if c2 is not None else m.player_2.character_id
                if m.winner is MatchupWinner.PLAYER_1:
                    role_note = f" ({_esc(player_names.get(p1_id, 'P1'))})"
                elif m.winner is MatchupWinner.PLAYER_2:
                    role_note = f" ({_esc(player_names.get(p2_id, 'P2'))})"
                else:
                    role_note = f" ({STATUS_DRAW})"
                lines.extend(
                    [
                        f"<b>✦ {_esc(m.role.title())}</b>{role_note}",
                        f"{p1_m} — {_esc(c1_name)} ({m.player_1.score})",
                        f"{p2_m} — {_esc(c2_name)} ({m.player_2.score})",
                        "",
                    ]
                )
        else:
            for role in ROLE_ORDER:
                cid1 = match.public_view.teams[p1_id].get(role)
                cid2 = match.public_view.teams[p2_id].get(role)
                if cid1 is None and cid2 is None:
                    continue
                c1_name = char_lookup[cid1].name if cid1 and cid1 in char_lookup else (cid1 or "—")
                c2_name = char_lookup[cid2].name if cid2 and cid2 in char_lookup else (cid2 or "—")
                lines.extend(
                    [
                        f"<b>✦ {_esc(role)}</b>",
                        f"{p1_m} — {_esc(c1_name)}",
                        f"{p2_m} — {_esc(c2_name)}",
                        "",
                    ]
                )
            if not any(
                match.public_view.teams[pid].get(r) is not None
                for pid in (p1_id, p2_id)
                for r in ROLE_ORDER
            ):
                lines.extend(["<i>No characters assigned.</i>", ""])

        lines.extend([SECTION_SEPARATOR, "", f"<b>{to_bold_serif_upper('CONCLUSION')}</b>", ""])
        if res is not None:
            if outcome.winner_id:
                winner_str = _mention(outcome.winner_id, player_names.get(outcome.winner_id))
            else:
                winner_str = STATUS_DRAW
            reason_label = {
                MatchOutcomeReason.NORMAL_MATCHUP_COUNT: "Role wins",
                MatchOutcomeReason.NORMAL_COMBINED_SCORE: "Total team score tiebreaker",
                MatchOutcomeReason.NORMAL_DRAW: "Exact draw",
            }.get(outcome.reason, outcome.reason.value)
            lines.extend(
                [
                    f"▪ <b>Winner:</b> {winner_str}",
                    f"▪ <b>Final score:</b> {res.summary.wins_player_1} — {res.summary.wins_player_2}",
                    f"▪ <b>Drawn roles:</b> {res.summary.draws}",
                    f"▪ <b>Duration:</b> {duration_str}",
                    f"▪ <b>Reason:</b> {_esc(reason_label)}",
                ]
            )
        else:
            winner_str = (
                _mention(outcome.winner_id, player_names.get(outcome.winner_id))
                if outcome.winner_id
                else "None"
            )
            reason_label = {
                MatchOutcomeReason.VOLUNTARY_FORFEITURE: "Forfeit",
                MatchOutcomeReason.INACTIVITY_VICTORY: "Turn timeout",
                MatchOutcomeReason.MUTUAL_INACTIVITY_ABANDONMENT: "Match abandoned (mutual inactivity)",
            }.get(outcome.reason, outcome.reason.value)
            lines.extend(
                [
                    f"▪ <b>Winner:</b> {winner_str}",
                    f"▪ <b>Duration:</b> {duration_str}",
                    f"▪ <b>Reason:</b> {_esc(reason_label)}",
                ]
            )

        lines.extend(["", f"<i>{_esc(self._timestamp_str())}</i>"])
        return await self._send_text(
            "\n".join(lines),
            dedup_key=f"TERMINAL:{match.match_id}:{tag}",
        )

    async def log_recovery(
        self,
        match: ManagedMatch,
        *,
        succeeded: bool,
        requester_id: str,
        player_names: Mapping[str, str],
        chat_id: str,
        group_title: str | None = None,
        group_username: str | None = None,
        detail: str = "",
    ) -> bool:
        tag = "#RECOVERED" if succeeded else "#RECOVERY_FAILED"
        req_m = _mention(requester_id, player_names.get(requester_id))
        lines = [
            f"<b>📋 {to_bold_serif_upper('MATCH LOG')}</b> · {tag}",
            "",
            f"◆ <b>Match ID:</b> <code>{_esc(match.match_id)}</code>",
            f"◆ <b>Requested by:</b> {req_m} (<code>{_esc(requester_id)}</code>)",
            f"◆ <b>Generation:</b> {match.generation}",
            "",
            *self._group_lines(
                chat_id=chat_id,
                group_title=group_title,
                group_username=group_username,
            ),
        ]
        if detail:
            lines.extend(["", f"▪ <b>Detail:</b> {_esc(detail)}"])
        lines.extend(["", f"<i>{_esc(self._timestamp_str())}</i>"])
        return await self._send_text(
            "\n".join(lines),
            dedup_key=f"{tag}:{match.match_id}:{match.generation}",
        )

    async def log_error(
        self,
        *,
        match_id: str | None = None,
        context: str,
        error_name: str,
    ) -> bool:
        lines = [
            f"<b>📋 {to_bold_serif_upper('MATCH LOG')}</b> · #ERROR",
            "",
        ]
        if match_id:
            lines.append(f"◆ <b>Match ID:</b> <code>{_esc(match_id)}</code>")
        lines.extend(
            [
                f"▪ <b>Context:</b> {_esc(context)}",
                f"▪ <b>Error:</b> <code>{_esc(error_name)}</code>",
                "",
                f"<i>{_esc(self._timestamp_str())}</i>",
            ]
        )
        return await self._send_text("\n".join(lines))
