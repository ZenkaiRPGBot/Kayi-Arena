"""Dedicated Kayi Arena Gameplay Logs (Arena Logs 2.0 — ARENA_LOG_CHANNEL_ID).

Sends compact, self-contained HTML match logs to a dedicated private Telegram
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
    ROLE_ICONS,
    ROLE_ORDER,
    SECTION_SEPARATOR,
    STATUS_DEFEAT,
    STATUS_DRAW,
    STATUS_NO_RESPONSE,
    STATUS_TIMEOUT,
    STATUS_VICTORY,
    to_bold_serif_upper,
    universe_icon,
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
        return self.clock().astimezone(IST).strftime("%d %b %Y · %I:%M:%S %p IST")

    @staticmethod
    def _group_line(
        *,
        chat_id: str,
        group_title: str | None,
        group_link: str | None = None,
    ) -> str:
        title_str = _esc(group_title) if group_title else "Unknown Group"
        if group_link:
            title_str = f'<a href="{_esc(group_link)}">{title_str}</a>'
        return f"<b>Group:</b> {title_str} (<code>{_esc(chat_id)}</code>)"

    async def log_match_started(
        self,
        match: ManagedMatch,
        **_: object,
    ) -> bool:
        """Deprecated in Arena Logs 2.0: match-start channel notifications are disabled."""
        return False

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
        del group_username  # Arena Logs 2.0 omits separate username line
        outcome = match.outcome
        if outcome is None:
            return False

        if outcome.reason in {
            MatchOutcomeReason.NORMAL_MATCHUP_COUNT,
            MatchOutcomeReason.NORMAL_COMBINED_SCORE,
            MatchOutcomeReason.NORMAL_DRAW,
        }:
            tag = "#COMPLETED"
            header = f"<b>📋 {to_bold_serif_upper('MATCH COMPLETED')}</b> · {tag}"
        elif outcome.reason is MatchOutcomeReason.VOLUNTARY_FORFEITURE:
            tag = "#FORFEITED"
            header = f"<b>🏳️ {to_bold_serif_upper('MATCH FORFEITED')}</b> · {tag}"
        elif outcome.reason is MatchOutcomeReason.INACTIVITY_VICTORY:
            tag = "#INACTIVITY"
            header = f"<b>⌛ {to_bold_serif_upper('INACTIVITY VICTORY')}</b> · {tag}"
        elif outcome.reason is MatchOutcomeReason.MUTUAL_INACTIVITY_ABANDONMENT:
            tag = "#ABANDONED"
            header = f"<b>🚫 {to_bold_serif_upper('MATCH ABANDONED')}</b> · {tag}"
        else:
            return await self.log_error(
                match_id=match.match_id,
                context="Terminal match resolution",
                error_name=outcome.reason.value,
                chat_id=chat_id,
                group_title=group_title,
                group_link=group_link,
                state_note="Match terminated",
                dedup_key=f"TERMINAL:{match.match_id}:#ERROR",
            )

        p1_id, p2_id = match.players
        p1_m = _mention(p1_id, player_names.get(p1_id))
        p2_m = _mention(p2_id, player_names.get(p2_id))
        u_icon = universe_icon(match.universe_id)
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
            header,
            "",
            f"◆ <b>Match ID:</b> <code>{_esc(match.match_id)}</code>",
            f"{u_icon} {_esc(universe_name)} · {mode_str} · {duration_str}",
            "",
            SECTION_SEPARATOR,
            "",
            self._group_line(chat_id=chat_id, group_title=group_title, group_link=group_link),
            "",
        ]

        res = outcome.resolution
        if res is not None:
            decided_by_label = {
                MatchOutcomeReason.NORMAL_MATCHUP_COUNT: "Role wins",
                MatchOutcomeReason.NORMAL_COMBINED_SCORE: "Total team score",
                MatchOutcomeReason.NORMAL_DRAW: "Equal role wins and team scores",
            }.get(outcome.reason, "Role wins")
            lines.extend(
                [
                    f"🔵 <b>{p1_m}</b> 〔{p1_status}〕 · <code>{_esc(p1_id)}</code>",
                    f"▸ <b>Score:</b> {res.summary.total_player_1}/700 · <b>Roles won:</b> {res.summary.wins_player_1}",
                    f"▸ <b>Skips:</b> {p1_skips_used}/2 · <b>Extensions:</b> {p1_ext_used}",
                    "",
                    f"🔴 <b>{p2_m}</b> 〔{p2_status}〕 · <code>{_esc(p2_id)}</code>",
                    f"▸ <b>Score:</b> {res.summary.total_player_2}/700 · <b>Roles won:</b> {res.summary.wins_player_2}",
                    f"▸ <b>Skips:</b> {p2_skips_used}/2 · <b>Extensions:</b> {p2_ext_used}",
                    "",
                    f"▸ <b>Drawn roles:</b> {res.summary.draws}",
                    f"▸ <b>Decided by:</b> {decided_by_label}",
                    "",
                    SECTION_SEPARATOR,
                    "",
                    f"<b>{to_bold_serif_upper('ROLE ASSIGNMENTS')}</b>",
                    "",
                ]
            )
            for idx, m in enumerate(res.matchups):
                if idx > 0:
                    lines.append("")
                role_title = m.role.title()
                r_icon = ROLE_ICONS.get(role_title, "🎭")
                c1 = char_lookup.get(m.player_1.character_id)
                c2 = char_lookup.get(m.player_2.character_id)
                c1_name = _esc(c1.name if c1 is not None else m.player_1.character_id)
                c2_name = _esc(c2.name if c2 is not None else m.player_2.character_id)
                s1 = m.player_1.score
                s2 = m.player_2.score
                if m.winner is MatchupWinner.PLAYER_1:
                    left_str = f"<b>〔{c1_name} · {s1}〕</b>"
                    right_str = f"{c2_name} · {s2}"
                elif m.winner is MatchupWinner.PLAYER_2:
                    left_str = f"{c1_name} · {s1}"
                    right_str = f"<b>〔{c2_name} · {s2}〕</b>"
                else:
                    left_str = f"{c1_name} · {s1}"
                    right_str = f"{c2_name} · {s2}"
                lines.append(f"{r_icon} <b>{_esc(role_title)}:</b> {left_str} — {right_str}")
        else:
            f1 = sum(1 for r in ROLE_ORDER if match.public_view.teams[p1_id].get(r) is not None)
            f2 = sum(1 for r in ROLE_ORDER if match.public_view.teams[p2_id].get(r) is not None)
            lines.extend(
                [
                    f"🔵 <b>{p1_m}</b> 〔{p1_status}〕 · <code>{_esc(p1_id)}</code>",
                    f"▸ <b>Assigned:</b> {f1}/7 · <b>Skips:</b> {p1_skips_used}/2 · <b>Extensions:</b> {p1_ext_used}",
                    "",
                    f"🔴 <b>{p2_m}</b> 〔{p2_status}〕 · <code>{_esc(p2_id)}</code>",
                    f"▸ <b>Assigned:</b> {f2}/7 · <b>Skips:</b> {p2_skips_used}/2 · <b>Extensions:</b> {p2_ext_used}",
                    "",
                ]
            )
            if tag == "#FORFEITED":
                forfeiter_id = outcome.forfeiting_player_id or ""
                forfeiter_m = _mention(forfeiter_id, player_names.get(forfeiter_id))
                lines.append(f"▸ <b>Reason:</b> {forfeiter_m} surrendered.")
            elif tag == "#INACTIVITY":
                inactive_id = outcome.inactive_player_id or ""
                winner_id = outcome.winner_id or ""
                inactive_m = _mention(inactive_id, player_names.get(inactive_id))
                winner_m = _mention(winner_id, player_names.get(winner_id))
                lines.extend(
                    [
                        f"▸ <b>Reason:</b> {inactive_m}'s turn expired.",
                        f"▸ <b>Decision:</b> Victory claimed by {winner_m}.",
                    ]
                )
            else:
                lines.extend(
                    [
                        "▸ <b>Reason:</b> Response window expired.",
                        "▸ <b>Result:</b> No win or loss recorded.",
                    ]
                )

            role_rows: list[str] = []
            for role in ROLE_ORDER:
                cid1 = match.public_view.teams[p1_id].get(role)
                cid2 = match.public_view.teams[p2_id].get(role)
                if cid1 is None and cid2 is None:
                    continue
                r_icon = ROLE_ICONS.get(role, "🎭")
                c1_name = _esc(
                    char_lookup[cid1].name if cid1 and cid1 in char_lookup else (cid1 or "Unassigned")
                )
                c2_name = _esc(
                    char_lookup[cid2].name if cid2 and cid2 in char_lookup else (cid2 or "Unassigned")
                )
                role_rows.append(f"{r_icon} <b>{_esc(role)}:</b> {c1_name} — {c2_name}")

            if role_rows:
                lines.extend(
                    [
                        "",
                        SECTION_SEPARATOR,
                        "",
                        f"<b>{to_bold_serif_upper('ROLE ASSIGNMENTS')}</b>",
                        "",
                    ]
                )
                for idx, row in enumerate(role_rows):
                    if idx > 0:
                        lines.append("")
                    lines.append(row)

        lines.extend(
            [
                "",
                SECTION_SEPARATOR,
                "",
                f"<b>Dataset:</b> <code>{_esc(match.dataset_version)}</code>",
                f"<i>{_esc(self._timestamp_str())}</i>",
            ]
        )
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
        group_link: str | None = None,
        stage: str = "",
        detail: str = "",
    ) -> bool:
        del group_username  # Arena Logs 2.0 omits separate username line
        req_m = _mention(requester_id, player_names.get(requester_id))
        group_line = self._group_line(
            chat_id=chat_id, group_title=group_title, group_link=group_link
        )
        if succeeded:
            lines = [
                f"<b>🔄 {to_bold_serif_upper('MATCH RECOVERED')}</b> · #RECOVERED",
                "",
                f"◆ <b>Match ID:</b> <code>{_esc(match.match_id)}</code>",
                "",
                group_line,
                "",
                f"<b>Requested by:</b> {req_m} (<code>{_esc(requester_id)}</code>)",
                "",
                f"<i>{_esc(self._timestamp_str())}</i>",
            ]
            dedup_key = f"#RECOVERED:{match.match_id}:{match.generation}"
        else:
            lines = [
                f"<b>⚠️ {to_bold_serif_upper('RECOVERY FAILED')}</b> · #RECOVERY_FAILED",
                "",
                f"◆ <b>Match ID:</b> <code>{_esc(match.match_id)}</code>",
                "",
                group_line,
                f"<b>Requested by:</b> {req_m} (<code>{_esc(requester_id)}</code>)",
                "",
                f"▸ <b>Stage:</b> {_esc(stage or 'Match recovery')}",
                f"▸ <b>Reason:</b> {_esc(detail or 'Telegram API request failed')}",
                "▸ <b>State:</b> Match preserved; recovery incomplete",
                "",
                f"<i>{_esc(self._timestamp_str())}</i>",
            ]
            dedup_key = f"#RECOVERY_FAILED:{match.match_id}:{match.generation}"
        return await self._send_text("\n".join(lines), dedup_key=dedup_key)

    async def log_error(
        self,
        *,
        match_id: str | None = None,
        context: str,
        error_name: str,
        chat_id: str | None = None,
        group_title: str | None = None,
        group_link: str | None = None,
        state_note: str | None = None,
        dedup_key: str | None = None,
    ) -> bool:
        lines = [
            f"<b>⚠️ {to_bold_serif_upper('GAMEPLAY ERROR')}</b> · #ERROR",
            "",
        ]
        if match_id:
            lines.append(f"◆ <b>Match ID:</b> <code>{_esc(match_id)}</code>")
        if chat_id:
            if match_id:
                lines.append("")
            lines.append(
                self._group_line(chat_id=chat_id, group_title=group_title, group_link=group_link)
            )
        lines.extend(
            [
                "",
                f"▸ <b>Operation:</b> {_esc(context)}",
                f"▸ <b>Error:</b> <code>{_esc(error_name)}</code>",
            ]
        )
        if state_note:
            lines.append(f"▸ <b>State:</b> {_esc(state_note)}")
        lines.extend(["", f"<i>{_esc(self._timestamp_str())}</i>"])
        return await self._send_text("\n".join(lines), dedup_key=dedup_key)
