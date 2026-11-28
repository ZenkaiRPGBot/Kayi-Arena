"""HTML presentation formatters for Kayi Arena Telegram UI.

All user-controlled strings are escaped via `html.escape`.
Messages are bounded to Telegram's 4096-char limit and photo captions to 1024 chars.
"""

from __future__ import annotations

import html
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Mapping, Sequence

from app.database import CharacterEntry, Universe
from app.matches import (
    ChallengeRecord,
    ChallengeStatus,
    ChallengeType,
    ManagedMatch,
    MatchLifecycleStatus,
    MatchOutcomeReason,
)
from app.resolution import DecidedBy, MatchOutcome, MatchupWinner
from app.telegram.constants import (
    MAX_CAPTION_LENGTH,
    MAX_MESSAGE_LENGTH,
    ROLE_ICONS,
    ROLE_ORDER,
    SECTION_SEPARATOR,
    STATUS_CURRENT_TURN,
    STATUS_DEFEAT,
    STATUS_DRAW,
    STATUS_NO_RESPONSE,
    STATUS_SKIPPED,
    STATUS_TIMEOUT,
    STATUS_VICTORY,
    rarity_icon,
    role_label,
    to_bold_serif_upper,
    to_small_caps_digits,
    universe_icon,
)

if TYPE_CHECKING:
    from app.persistence.models import HistoricalMatchRecord, PlayerStatsSummary

_IST = timezone(timedelta(hours=5, minutes=30))
from app.telegram.ports import (
    LeaderboardEntryView,
    MatchHistoryEntryView,
    PlayerProfileView,
)


def esc(value: object) -> str:
    """Escape text safely for Telegram HTML parse mode."""
    return html.escape(str(value or ""), quote=True)


def clamp_text(text: str, limit: int = MAX_MESSAGE_LENGTH) -> str:
    """Clamp rendered output to Telegram's character limit."""
    if len(text) <= limit:
        return text
    if limit <= 1:
        return text[:limit]
    return text[: limit - 1] + "…"


def clamp_caption(text: str) -> str:
    return clamp_text(text, MAX_CAPTION_LENGTH)


def format_mode_label(game_mode: str) -> str:
    return "🏆 Ranked" if game_mode == "ranked" else "🤝 Friendly"


def format_duration_short(seconds: float) -> str:
    secs = max(0, int(round(seconds)))
    if secs >= 60 and secs % 60 == 0:
        mins = secs // 60
        return f"{mins} minute" if mins == 1 else f"{mins} minutes"
    if secs >= 60:
        mins, rem = divmod(secs, 60)
        return f"{mins}m {rem}s"
    return f"{secs}s"


def format_deadline_countdown(seconds_remaining: float) -> str:
    secs = max(0, int(round(seconds_remaining)))
    if secs == 0:
        return "Expired"
    mins, rem = divmod(secs, 60)
    if mins > 0:
        return f"{mins}m {rem:02d}s remaining"
    return f"{rem}s remaining"


# ---------------------------------------------------------------------------
# Home & Help
# ---------------------------------------------------------------------------


def render_home_private() -> str:
    return clamp_caption(
        "\n".join(
            [
                "⚔️ <b>Welcome to Kayi Arena</b>",
                "",
                "A battlefield where anime universes collide and strategy decides your fate.",
                "",
                "Assemble your dream team, master seven unique roles, and outsmart your opponents in strategic 1v1 battles.",
                "",
                "Every character matters. Every decision counts.",
                "",
                "⚔️ /arena — Begin your battle",
                "📖 /help — Learn the game",
                "",
                "<i>Power is given. Victory is earned.</i>",
                "",
                "<i>Powered by Kayi Bots</i>",
            ]
        )
    )


def render_support_home() -> str:
    return clamp_text(
        "\n".join(
            [
                "<b>💬 Kayi Arena Support</b>",
                "",
                "Encountered an issue or have an idea to improve the arena?",
                "",
                "We'd love to hear from you.",
            ]
        )
    )


def render_home_group() -> str:
    return clamp_text(
        "\n".join(
            [
                "⚔️ <b>KAYI ARENA</b>",
                "",
                "Draft anime characters into seven strategic roles and battle other players 1v1.",
                "",
                "Use <code>/arena</code> to pick a universe, <code>/arena &lt;universe&gt;</code> or reply to a player to challenge them directly, and <code>/help</code> for the full guide.",
            ]
        )
    )


def _format_rarity_pct(weight: float) -> str:
    if weight == int(weight):
        return f"{int(weight)}%"
    return f"{weight:g}%"


def _build_handbook_chapters() -> dict[str, str]:
    from app.database.models import DEFAULT_RARITY_WEIGHTS

    total_w = sum(DEFAULT_RARITY_WEIGHTS.values()) or 100.0
    def _pct(tier: str) -> str:
        raw = DEFAULT_RARITY_WEIGHTS.get(tier, 0.0)
        return _format_rarity_pct((raw / total_w) * 100.0 if abs(total_w - 100.0) > 1e-6 else raw)

    return {
        "menu": "\n".join(
            [
                "<b>📖 The Arena Handbook</b>",
                "",
                "Your guide to playing Kayi Arena.",
                "",
                "<b>01</b> — Getting Started",
                "<b>02</b> — Building Your Team",
                "<b>03</b> — Understanding Roles",
                "<b>04</b> — Character Rarity",
                "<b>05</b> — Winning the Battle",
                "<b>06</b> — Match Rules",
                "",
                "<i>Select a chapter to continue.</i>",
            ]
        ),
        "1": "\n".join(
            [
                "<i>THE ARENA HANDBOOK · 01/06</i>",
                "",
                "<b>Getting Started</b>",
                "",
                "Kayi Arena is a two-player strategy game where you build a team of anime characters and compete against another player.",
                "",
                "Each team has seven characters, with one character assigned to each role.",
                "",
                "<b>How to start a match</b>",
                "",
                "Battles begin in groups. Add the bot to a group, then:",
                "",
                "To challenge someone directly, reply to their message with /arena.",
                "",
                "To invite anyone in the group to play, send /arena without replying to a message.",
                "",
                "Choose a universe and match mode, then send your challenge.",
                "",
                "Once your opponent accepts, the game begins!",
            ]
        ),
        "2": "\n".join(
            [
                "<i>THE ARENA HANDBOOK · 02/06</i>",
                "",
                "<b>Building Your Team</b>",
                "",
                "Both players take turns choosing characters for their teams.",
                "",
                "<b>Shuffle</b>",
                "",
                "Press Shuffle to receive a random character from the selected anime universe.",
                "",
                "<b>Assign</b>",
                "",
                "Choose an available role for the character. Once assigned, the character cannot be moved or replaced.",
                "",
                "<b>Skip</b>",
                "",
                "Don't want the character? Use a skip, then press Shuffle to receive another character. You have two skips per match.",
                "",
                "After assigning a character, your opponent takes their turn.",
                "",
                "The battle begins automatically when both teams are complete.",
                "",
                "⏳ Each turn lasts 2 minutes.",
            ]
        ),
        "3": "\n".join(
            [
                "<i>THE ARENA HANDBOOK · 03/06</i>",
                "",
                "<b>Understanding Roles</b>",
                "",
                "Every character has different strengths. Choosing the right role is just as important as getting a powerful character.",
                "",
                "<b>👑 Captain</b>",
                "Leads the team and guides others during battle.",
                "",
                "<b>🧠 Strategist</b>",
                "Creates plans, studies opponents and makes smart decisions.",
                "",
                "<b>⚔️ Attacker</b>",
                "Uses powerful attacks to defeat enemies.",
                "",
                "<b>🛡️ Tank</b>",
                "Withstands heavy attacks and protects the team.",
                "",
                "<b>🗡️ Assassin</b>",
                "Specializes in surprise attacks and eliminating specific enemies.",
                "",
                "<b>✨ Support</b>",
                "Helps teammates by improving their abilities or limiting enemies.",
                "",
                "<b>💚 Healer</b>",
                "Treats injuries and helps teammates recover.",
                "",
                "For example, Shikamaru may be a better Strategist than a much stronger fighter.",
            ]
        ),
        "4": "\n".join(
            [
                "<i>THE ARENA HANDBOOK · 04/06</i>",
                "",
                "<b>Character Rarity</b>",
                "",
                "Characters are divided into five rarity levels based on their power and abilities.",
                "",
                f"⚪ Common — {_pct('Common')}",
                f"🟢 Uncommon — {_pct('Uncommon')}",
                f"🔵 Rare — {_pct('Rare')}",
                f"🟣 Epic — {_pct('Epic')}",
                f"🟡 Legendary — {_pct('Legendary')}",
                "",
                "These are the chances of receiving a character from each rarity level when all five levels are available. The chances adjust when a rarity level runs out of available characters.",
                "",
                "<b>Does higher rarity always mean a better character?</b>",
                "",
                "No. A character with lower rarity can defeat a Legendary character if they are better suited to their assigned role.",
                "",
                "Always consider the character's abilities before choosing a role.",
            ]
        ),
        "5": "\n".join(
            [
                "<i>THE ARENA HANDBOOK · 05/06</i>",
                "",
                "<b>Winning the Battle</b>",
                "",
                "When both teams are complete, the game compares characters assigned to the same role.",
                "",
                "Your Captain faces their Captain, your Attacker faces their Attacker, and so on.",
                "",
                "Each character receives a score based on their overall power and how suitable they are for the assigned role.",
                "",
                "<b>Example Battle</b>",
                "",
                "👑 Captain — <b>80</b> vs 72",
                "🧠 Strategist — <b>91</b> vs 63",
                "⚔️ Attacker — 80 vs <b>90</b>",
                "🛡️ Tank — 60 vs <b>90</b>",
                "🗡️ Assassin — <b>87</b> vs 80",
                "✨ Support — 80 vs 80",
                "💚 Healer — <b>97</b> vs 60",
                "",
                "<b>4 — 2</b>",
                "",
                "🏆 <b>You win!</b>",
                "",
                "4 wins · 2 losses · 1 draw",
                "",
                "<b>What happens if both players have equal wins?</b>",
                "",
                "The player with the higher total team score wins. If the total scores are also equal, the match ends in a draw.",
            ]
        ),
        "6": "\n".join(
            [
                "<i>THE ARENA HANDBOOK · 06/06</i>",
                "",
                "<b>Match Rules</b>",
                "",
                "<b>Ranked &amp; Friendly Matches</b>",
                "",
                "Ranked matches are intended for competitive play. Friendly matches allow you to play without affecting your competitive ranking.",
                "",
                "<b>Running out of time</b>",
                "",
                "If you fail to assign a character within 2 minutes, your opponent has 60 seconds to claim victory or grant you an extra minute.",
                "",
                "Each player can receive one extension per match.",
                "",
                "If your opponent does not respond within 60 seconds, the match ends without a winner.",
                "",
                "<b>Leaving a match</b>",
                "",
                "You can use /game to return to your active match or surrender. Surrendering counts as a loss.",
                "",
                "<b>Important rules</b>",
                "",
                "• Only one active match is allowed per player.",
                "• Each character can appear only once in a match.",
                "• Assigned characters cannot be replaced.",
                "• Shuffling and skipping do not reset your timer.",
                "• Unaccepted challenges expire after 5 minutes.",
            ]
        ),
    }


def render_help_topic(topic: str = "menu") -> str:
    chapters = _build_handbook_chapters()
    text = chapters.get(topic, chapters["menu"])
    return clamp_text(text)


# ---------------------------------------------------------------------------
# Universe Selection & Challenge
# ---------------------------------------------------------------------------


def render_arena_private() -> str:
    return clamp_text(
        "\n".join(
            [
                "<b>⚔️ Enter the Arena</b>",
                "",
                "Battles can only be played in groups.",
                "",
                "Add me to a group and use /arena to challenge another player.",
            ]
        )
    )


def render_arena_config(
    *,
    selected_universe_id: str | None,
    universe_name: str | None,
    game_mode: str,
) -> str:
    if selected_universe_id is None:
        universe_line = "Not selected"
    elif selected_universe_id == "random":
        universe_line = "🎲 Random"
    else:
        icon = universe_icon(selected_universe_id)
        universe_line = f"{icon} {esc(universe_name or selected_universe_id)}"

    mode_line = "🏆 Ranked" if game_mode == "ranked" else "🤝 Friendly"
    lines = [
        "<b>⚔️ Kayi Arena</b>",
        "",
        "Choose your battle preferences.",
        "",
        f"<b>Universe:</b> {universe_line}",
        "",
        f"<b>Match Mode:</b> {mode_line}",
    ]
    if selected_universe_id == "random":
        lines.extend(
            [
                "",
                "<i>The universe will be revealed when the challenge is accepted.</i>",
            ]
        )
    return clamp_text("\n".join(lines))


def render_universe_browser(*, has_universes: bool = True) -> str:
    if not has_universes:
        return clamp_text(
            "\n".join(
                [
                    "🌐 <b>No Eligible Universes Available</b>",
                    "",
                    "There are currently no active universes with published character datasets.",
                    "Please check back once a universe dataset is published.",
                ]
            )
        )
    return clamp_text(
        "\n".join(
            [
                "<b>🌐 Select a Universe</b>",
                "",
                "Choose the universe you want to battle in.",
            ]
        )
    )


def render_invalid_universe(universe_arg: str, *, has_eligible_universes: bool) -> str:
    lines = [
        "<b>⚠️ Universe Not Found</b>",
        "",
        f"{esc(universe_arg)} is not an available universe.",
        "",
        "Please select an available universe."
        if has_eligible_universes
        else "No playable universes are currently available.",
    ]
    return clamp_text("\n".join(lines))


def render_universe_selection(
    *,
    universes: Sequence[Universe],
    game_mode: str,
    target_player_name: str | None = None,
) -> str:
    if not universes:
        return clamp_text(
            "\n".join(
                [
                    "🌐 <b>No Eligible Universes Available</b>",
                    "",
                    "There are currently no active universes with published character datasets.",
                    "Please check back once a universe dataset is published.",
                ]
            )
        )

    lines = [
        "🌐 <b>Select a universe</b>",
        "",
        "Choose the anime universe for your next draft battle.",
        "",
        format_mode_label(game_mode),
    ]
    if target_player_name:
        lines.append(f"🎯 Direct challenge target: <b>{esc(target_player_name)}</b>")
    count = len(universes)
    noun = "universe" if count == 1 else "universes"
    lines.append(f"{count} {noun} available")
    return clamp_text("\n".join(lines))


def format_user_mention(user_id: str | int, first_name: str | None) -> str:
    """Render a clickable Telegram tg://user mention using escaped first_name."""
    uid_str = str(user_id).strip()
    label = (first_name or "").strip()
    if not label or label == uid_str:
        label = "Player"
    safe_label = esc(label)
    if uid_str.isdigit():
        return f'<a href="tg://user?id={uid_str}">{safe_label}</a>'
    return safe_label


def _format_challenge_ttl(seconds: float) -> str:
    total = max(1, int(round(seconds)))
    if total >= 60 and total % 60 == 0:
        mins = total // 60
        return "1 minute" if mins == 1 else f"{mins} minutes"
    if total >= 60:
        mins = total // 60
        return "1 minute" if mins == 1 else f"{mins} minutes"
    return "1 second" if total == 1 else f"{total} seconds"


def render_challenge_card(
    challenge: ChallengeRecord,
    *,
    universe_name: str,
    challenger_name: str,
    target_name: str | None = None,
    seconds_remaining: float = 300.0,
) -> str:
    challenger_mention = format_user_mention(challenge.challenger_id, challenger_name)
    opponent_mention = (
        format_user_mention(challenge.target_player_id, target_name)
        if challenge.target_player_id
        else "Player"
    )

    if challenge.status is ChallengeStatus.DECLINED:
        return clamp_text(
            "\n".join(
                [
                    "<b>Challenge Declined</b>",
                    "",
                    f"{opponent_mention} declined the challenge.",
                ]
            )
        )

    if challenge.status is ChallengeStatus.CANCELLED:
        return clamp_text(
            "\n".join(
                [
                    "<b>❌ Challenge Cancelled</b>",
                    "",
                    f"{challenger_mention} cancelled the challenge.",
                ]
            )
        )

    if challenge.status is ChallengeStatus.EXPIRED:
        return clamp_text(
            "\n".join(
                [
                    "<b>⌛ Challenge Expired</b>",
                    "",
                    "The challenge was not accepted in time.",
                ]
            )
        )

    u_icon = universe_icon(challenge.universe_id)
    mode_line = "🏆 Ranked" if challenge.game_mode == "ranked" else "🤝 Friendly"

    if challenge.status is ChallengeStatus.ACCEPTED:
        return clamp_text(
            "\n".join(
                [
                    "✅ <b>Challenge Accepted</b> — Match started!",
                    "",
                    f"<b>Universe:</b> {u_icon} {esc(universe_name)}",
                    f"<b>Mode:</b> {mode_line}",
                ]
            )
        )

    is_direct = challenge.challenge_type is ChallengeType.DIRECT and challenge.target_player_id
    ttl_seconds = max(1.0, seconds_remaining if seconds_remaining > 0 else (challenge.expires_at - challenge.created_at))
    ttl_str = _format_challenge_ttl(ttl_seconds)

    if is_direct:
        lines = [
            "<b>⚔️ Battle Challenge</b>",
            "",
            f"{challenger_mention} has challenged {opponent_mention} to a battle.",
            "",
            f"<b>Universe:</b> {u_icon} {esc(universe_name)}",
            "",
            f"<b>Mode:</b> {mode_line}",
        ]
    else:
        lines = [
            "<b>⚔️ Open Challenge</b>",
            "",
            f"{challenger_mention} is looking for an opponent.",
            "",
            f"<b>Universe:</b> {u_icon} {esc(universe_name)}",
            "",
            f"<b>Mode:</b> {mode_line}",
        ]

    if challenge.universe_id == "random":
        lines.extend(["", "<i>The universe will be revealed upon acceptance.</i>"])

    lines.extend(["", f"<i>⏳ Expires in {ttl_str}.</i>"])
    return clamp_text("\n".join(lines))


# ---------------------------------------------------------------------------
# Draft Board & Character Cards (Screens 01-07)
# ---------------------------------------------------------------------------


def _format_timer_value(seconds_remaining: float) -> str:
    secs = max(0, int(round(seconds_remaining)))
    if secs >= 60 and secs % 60 == 0:
        mins = secs // 60
        return "1 minute" if mins == 1 else f"{mins} minutes"
    if secs >= 60:
        mins, rem = divmod(secs, 60)
        return f"{mins}m {rem}s"
    return f"{secs}s"


def _format_countdown_compact(seconds_remaining: float) -> str:
    secs = max(0, int(round(seconds_remaining)))
    if secs >= 60:
        mins, rem = divmod(secs, 60)
        return f"{mins}m {rem:02d}s" if rem else f"{mins}m 00s"
    return f"{secs}s"


def _render_player_board_section(
    *,
    marker: str,
    player_id: str,
    player_name: str,
    assignments: Mapping[str, str | None],
    skips_remaining: int,
    char_lookup: Mapping[str, CharacterEntry],
    is_active: bool,
    in_timeout_decision: bool,
) -> list[str]:
    filled = sum(1 for role in ROLE_ORDER if assignments.get(role) is not None)
    mention = format_user_mention(player_id, player_name)
    turn_suffix = ""
    if is_active:
        turn_suffix = f" ✦ {STATUS_TIMEOUT}" if in_timeout_decision else f" ✦ {STATUS_CURRENT_TURN}"

    lines = [f"{marker} <b>{mention}</b> 〔{filled}/7〕{turn_suffix}", ""]
    if filled == 0:
        lines.append("<i>No characters assigned.</i>")
    else:
        assigned_lines: list[str] = []
        for role in ROLE_ORDER:
            cid = assignments.get(role)
            if cid is None:
                continue
            rec = char_lookup.get(cid)
            r_icon = ROLE_ICONS.get(role, "🎭")
            if rec is not None:
                rar_icon = rarity_icon(rec.rarity)
                assigned_lines.append(f"✦ {r_icon} <b>{esc(role)}</b> — <b>{esc(rec.name)}</b> {rar_icon}")
            else:
                assigned_lines.append(f"✦ {r_icon} <b>{esc(role)}</b> — <b>{esc(cid)}</b>")
        for idx, entry_line in enumerate(assigned_lines):
            if idx > 0:
                lines.append("")
            lines.append(entry_line)
    available_icons = [ROLE_ICONS[role] for role in ROLE_ORDER if assignments.get(role) is None]
    avail_text = " ".join(available_icons) if available_icons else "None"
    lines.extend(
        [
            "",
            f"▸ <b>Available:</b> {avail_text}",
            f"▸ <b>Skips left:</b> {skips_remaining}/2",
        ]
    )
    return lines


def render_draft_board(
    match: ManagedMatch,
    *,
    universe_name: str,
    player_names: Mapping[str, str],
    char_lookup: Mapping[str, CharacterEntry],
    seconds_remaining: float = 0.0,
    last_action_line: str | None = None,
) -> str:
    p1_id, p2_id = match.players
    p1_name = player_names.get(p1_id, p1_id)
    p2_name = player_names.get(p2_id, p2_id)
    pv = match.public_view
    u_icon = universe_icon(match.universe_id)
    active_id = pv.active_player_id
    in_timeout_decision = match.inactivity_claim_offered_to is not None

    lines = [
        f"<b>⚔️ {to_bold_serif_upper('KAYI ARENA')}</b>",
        "",
        f"◆ <b>Universe</b> — {u_icon} {esc(universe_name)}",
        f"◆ <b>Mode</b> — {format_mode_label(match.game_mode)}",
        "",
        SECTION_SEPARATOR,
        "",
        *_render_player_board_section(
            marker="🔵",
            player_id=p1_id,
            player_name=p1_name,
            assignments=pv.teams[p1_id],
            skips_remaining=pv.skips_remaining[p1_id],
            char_lookup=char_lookup,
            is_active=(active_id == p1_id),
            in_timeout_decision=in_timeout_decision,
        ),
        "",
        SECTION_SEPARATOR,
        "",
        *_render_player_board_section(
            marker="🔴",
            player_id=p2_id,
            player_name=p2_name,
            assignments=pv.teams[p2_id],
            skips_remaining=pv.skips_remaining[p2_id],
            char_lookup=char_lookup,
            is_active=(active_id == p2_id),
            in_timeout_decision=in_timeout_decision,
        ),
    ]
    return clamp_text("\n".join(lines))


def render_awaiting_shuffle_card(
    match: ManagedMatch,
    *,
    player_names: Mapping[str, str],
    seconds_remaining: float | None = None,
) -> str:
    active_id = match.draft_snapshot.active_player_id or ""
    active_mention = format_user_mention(active_id, player_names.get(active_id))
    ds = match.display_state
    rem = (
        seconds_remaining
        if seconds_remaining is not None
        else max(0.0, match.turn_deadline_at - match.turn_started_at)
    )

    # Screen 07 Variation A (extended turn before draw)
    if ds.extension_granted_note and ds.last_action != "skipped":
        opponent_id = match.players[1] if match.players[0] == active_id else match.players[0]
        opp_mention = format_user_mention(opponent_id, player_names.get(opponent_id))
        has_any_char = ds.last_character_id is not None
        which = "next" if has_any_char else "first"
        time_label = _format_timer_value(rem) if rem < 59.0 else "60 seconds"
        return clamp_caption(
            "\n".join(
                [
                    f"<b>⏳ {to_bold_serif_upper('TURN EXTENDED')}</b>",
                    "",
                    f"{opp_mention} gave {active_mention} another minute.",
                    "",
                    f"{active_mention}, Shuffle to reveal your {which} character.",
                    "",
                    f"▪ <b>Time limit:</b> {time_label}",
                    "",
                    "<i>This is your final extension.</i>",
                ]
            )
        )

    # Screen 05 / 07 Variation C (character previously skipped, artwork retained)
    if ds.last_action == "skipped" and ds.last_character_name:
        r_icon = rarity_icon(ds.last_character_rarity or "Common")
        skips = match.public_view.skips_remaining.get(active_id, 0)
        lines = [
            f"<b>✦ {to_bold_serif_upper(ds.last_character_name)}</b>",
            "",
            f"{r_icon} <b>{esc(ds.last_character_rarity or 'Common')}</b> · ⏭ {STATUS_SKIPPED}",
        ]
        if ds.extension_granted_note:
            opponent_id = match.players[1] if match.players[0] == active_id else match.players[0]
            opp_mention = format_user_mention(opponent_id, player_names.get(opponent_id))
            lines.extend(["", f"⏳ {opp_mention} granted an extra minute."])
        lines.extend(
            [
                "",
                SECTION_SEPARATOR,
                "",
                f"{active_mention}, Shuffle to reveal another character.",
                "",
                f"▪ <b>Skips left:</b> {skips}/2",
                f"▪ <b>Time remaining:</b> {_format_countdown_compact(rem)}",
            ]
        )
        if ds.extension_granted_note:
            lines.extend(["", "<i>This is your final extension.</i>"])
        return clamp_caption("\n".join(lines))

    # Screen 04 (previous character assigned, artwork retained, next player's Shuffle)
    if ds.last_action == "assigned" and ds.last_character_name and ds.assigned_role:
        r_icon = rarity_icon(ds.last_character_rarity or "Common")
        assigner_id = ds.assigned_by_player_id or ""
        assigner_mention = format_user_mention(assigner_id, player_names.get(assigner_id))
        time_label = (
            _format_timer_value(rem)
            if rem < (match.timeout_policy.turn_timeout_seconds - 1.0)
            else _format_timer_value(match.timeout_policy.turn_timeout_seconds)
        )
        return clamp_caption(
            "\n".join(
                [
                    f"<b>✦ {to_bold_serif_upper(ds.last_character_name)}</b>",
                    "",
                    f"{r_icon} <b>{esc(ds.last_character_rarity or 'Common')}</b>",
                    "",
                    f"✅ Assigned as <b>{esc(ds.assigned_role)}</b> by {assigner_mention}.",
                    "",
                    SECTION_SEPARATOR,
                    "",
                    f"{active_mention}, Shuffle to reveal your next character.",
                    "",
                    f"▪ <b>Time limit:</b> {time_label}",
                ]
            )
        )

    # Screen 02 (Initial Shuffle, text-only)
    time_label = (
        _format_timer_value(rem)
        if rem < (match.timeout_policy.turn_timeout_seconds - 1.0)
        else _format_timer_value(match.timeout_policy.turn_timeout_seconds)
    )
    return clamp_caption(
        "\n".join(
            [
                f"<b>🎲 {to_bold_serif_upper('CHARACTER DRAFT')}</b>",
                "",
                f"{active_mention}, Shuffle to reveal your first character.",
                "",
                f"▪ <b>Time limit:</b> {time_label}",
            ]
        )
    )


def render_revealed_character_card(
    match: ManagedMatch,
    *,
    character: CharacterEntry,
    universe_name: str,
    player_names: Mapping[str, str],
    seconds_remaining: float | None = None,
) -> str:
    """Render Screen 03 / 07B caption. NEVER exposes Power, Fits, scores, or RP."""
    active_id = match.draft_snapshot.active_player_id or ""
    active_mention = format_user_mention(active_id, player_names.get(active_id))
    skips = match.public_view.skips_remaining.get(active_id, 0)
    r_icon = rarity_icon(character.rarity)
    rem = (
        seconds_remaining
        if seconds_remaining is not None
        else max(0.0, match.turn_deadline_at - match.turn_started_at)
    )

    lines = [
        f"<b>✦ {to_bold_serif_upper(character.name)}</b>",
        "",
        f"{r_icon} <b>{esc(character.rarity)}</b>",
    ]
    if match.display_state.extension_granted_note:
        opponent_id = match.players[1] if match.players[0] == active_id else match.players[0]
        opp_mention = format_user_mention(opponent_id, player_names.get(opponent_id))
        lines.extend(["", f"⏳ {opp_mention} granted an extra minute."])

    lines.extend(
        [
            "",
            SECTION_SEPARATOR,
            "",
            f"{active_mention}, choose a role for your character.",
            "",
            f"▪ <b>Skips left:</b> {skips}/2",
            f"▪ <b>Time remaining:</b> {_format_countdown_compact(rem)}",
        ]
    )
    if match.display_state.extension_granted_note:
        lines.extend(["", "<i>This is your final extension.</i>"])
    return clamp_caption("\n".join(lines))


def render_turn_expired_card(
    match: ManagedMatch,
    *,
    player_names: Mapping[str, str],
    seconds_remaining: float | None = None,
) -> str:
    inactive_id = match.draft_snapshot.active_player_id or ""
    opponent_id = match.inactivity_claim_offered_to or ""
    inactive_mention = format_user_mention(inactive_id, player_names.get(inactive_id))
    opponent_mention = format_user_mention(opponent_id, player_names.get(opponent_id))
    claim_secs = (
        max(1, int(round(seconds_remaining)))
        if seconds_remaining is not None
        else int(match.timeout_policy.claim_window_seconds)
    )
    has_extension = match.extensions_remaining.get(inactive_id, 0) > 0

    times_up_hdr = to_bold_serif_upper("TIME'S UP")
    lines = [
        f"<b>⌛ {times_up_hdr}</b>",
        "",
        f"{inactive_mention} failed to complete their turn.",
        "",
    ]
    if has_extension:
        lines.append(f"{opponent_mention}, claim victory or grant extra time.")
    else:
        lines.extend(
            [
                f"{opponent_mention}, you may now claim victory.",
                "",
                "<i>No further extensions are available.</i>",
            ]
        )
    lines.extend(
        [
            "",
            f"<i>The match will end without a winner if you don't respond within {claim_secs} seconds.</i>",
        ]
    )
    return clamp_caption("\n".join(lines))


def render_retired_card_text(match: ManagedMatch, *, player_names: Mapping[str, str]) -> str:
    if match.status is MatchLifecycleStatus.COMPLETED and match.outcome and match.outcome.winner_id:
        w_m = format_user_mention(match.outcome.winner_id, player_names.get(match.outcome.winner_id))
        return clamp_caption(f"<b>{to_bold_serif_upper('ARENA RESULT')}</b> — {w_m} ({STATUS_VICTORY})")
    if match.status is MatchLifecycleStatus.COMPLETED:
        return clamp_caption(f"<b>{to_bold_serif_upper('ARENA RESULT')}</b> — {STATUS_DRAW}")
    if match.status is MatchLifecycleStatus.FORFEITED:
        return clamp_caption(f"<b>{to_bold_serif_upper('ARENA RESULT')}</b> — Forfeit")
    if match.status is MatchLifecycleStatus.INACTIVITY_WIN:
        return clamp_caption(f"<b>{to_bold_serif_upper('ARENA RESULT')}</b> — Turn timeout")
    if match.status is MatchLifecycleStatus.ABANDONED:
        return clamp_caption(f"<b>{to_bold_serif_upper('ARENA RESULT')}</b> — Match abandoned")
    return clamp_caption(f"<b>{to_bold_serif_upper('ARENA RESULT')}</b>")


# ---------------------------------------------------------------------------
# Match Results & Battle Breakdown (Screens 08-12, 14)
# ---------------------------------------------------------------------------


def render_match_results(
    match: ManagedMatch,
    *,
    universe_name: str,
    player_names: Mapping[str, str],
    char_lookup: Mapping[str, CharacterEntry] | None = None,
) -> str:
    outcome = match.outcome
    u_icon = universe_icon(match.universe_id)
    p1_id, p2_id = match.players
    p1_mention = format_user_mention(p1_id, player_names.get(p1_id))
    p2_mention = format_user_mention(p2_id, player_names.get(p2_id))
    chars = char_lookup or {}

    if outcome is None:
        return clamp_text(f"<b>⚔️ {to_bold_serif_upper('ARENA RESULT')}</b>")

    # Early / non-normal outcomes (Screens 08, 09, 14) — NEVER invent scores.
    if outcome.resolution is None:
        mode_label = format_mode_label(match.game_mode)
        if outcome.reason is MatchOutcomeReason.VOLUNTARY_FORFEITURE:
            winner_id = outcome.winner_id or ""
            forfeiter_id = outcome.forfeiting_player_id or ""
            winner_m = format_user_mention(winner_id, player_names.get(winner_id))
            forfeiter_m = format_user_mention(forfeiter_id, player_names.get(forfeiter_id))
            body = [
                f"🟢 <b>{winner_m}</b> 〔{STATUS_VICTORY}〕",
                "",
                f"🔴 <b>{forfeiter_m}</b> 〔{STATUS_DEFEAT}〕",
                "",
                SECTION_SEPARATOR,
                "",
                "▪ <b>Reason:</b> Forfeit",
                "",
                f"<i>{forfeiter_m} surrendered the match.</i>",
            ]
        elif outcome.reason is MatchOutcomeReason.INACTIVITY_VICTORY:
            winner_id = outcome.winner_id or ""
            inactive_id = outcome.inactive_player_id or ""
            winner_m = format_user_mention(winner_id, player_names.get(winner_id))
            inactive_m = format_user_mention(inactive_id, player_names.get(inactive_id))
            body = [
                f"🟢 <b>{winner_m}</b> 〔{STATUS_VICTORY}〕",
                "",
                f"🔴 <b>{inactive_m}</b> 〔{STATUS_DEFEAT}〕",
                "",
                SECTION_SEPARATOR,
                "",
                "▪ <b>Reason:</b> Turn timeout",
                "",
                "<i>Victory claimed by the opponent.</i>",
            ]
        elif outcome.reason is MatchOutcomeReason.MUTUAL_INACTIVITY_ABANDONMENT:
            timed_out_id = outcome.inactive_player_id or match.draft_snapshot.active_player_id or p1_id
            other_id = p2_id if timed_out_id == p1_id else p1_id
            timed_out_m = format_user_mention(timed_out_id, player_names.get(timed_out_id))
            other_m = format_user_mention(other_id, player_names.get(other_id))
            body = [
                f"🔵 <b>{timed_out_m}</b> 〔{STATUS_TIMEOUT}〕",
                "",
                f"🔴 <b>{other_m}</b> 〔{STATUS_NO_RESPONSE}〕",
                "",
                SECTION_SEPARATOR,
                "",
                "▪ <b>Result:</b> Match abandoned",
                "",
                "<i>The match ended without a winner. No win or loss recorded.</i>",
            ]
        else:
            body = [
                f"🔵 <b>{p1_mention}</b>",
                "",
                f"🔴 <b>{p2_mention}</b>",
                "",
                SECTION_SEPARATOR,
                "",
                "▪ <b>Result:</b> Match terminated",
            ]

        return clamp_text(
            "\n".join(
                [
                    f"<b>⚔️ {to_bold_serif_upper('ARENA RESULT')}</b>",
                    "",
                    f"◆ <b>Universe</b> — {u_icon} {esc(universe_name)}",
                    f"◆ <b>Mode</b> — {mode_label}",
                    "",
                    SECTION_SEPARATOR,
                    "",
                    *body,
                ]
            )
        )

    # Completed Battle Result (Screens 10 & 12) — NO emojis anywhere!
    res = outcome.resolution
    summary = res.summary
    mode_plain = "Ranked" if match.game_mode == "ranked" else "Friendly"
    score_badge = f"〔{to_bold_serif_upper(str(summary.wins_player_1))} — {to_bold_serif_upper(str(summary.wins_player_2))}〕"

    if res.outcome is MatchOutcome.PLAYER_1_WIN:
        outcome_line = f"✦ <b>{p1_mention}</b> — {STATUS_VICTORY}"
        winner_mention = p1_mention
    elif res.outcome is MatchOutcome.PLAYER_2_WIN:
        outcome_line = f"✦ <b>{p2_mention}</b> — {STATUS_VICTORY}"
        winner_mention = p2_mention
    else:
        outcome_line = f"✦ <b>{to_bold_serif_upper('BATTLE DRAW')}</b>"
        winner_mention = ""

    if res.decided_by is DecidedBy.MATCHUP_COUNT:
        explanation = "<i>Victory by role wins.</i>"
    elif res.decided_by is DecidedBy.COMBINED_SCORE:
        explanation = f"<i>Both players won an equal number of roles. {winner_mention} wins by a higher total team score.</i>"
    else:
        explanation = "<i>Both players finished with equal role wins and equal team scores.</i>"

    lines = [
        f"<b>{to_bold_serif_upper('ARENA RESULT')}</b>",
        "",
        f"◆ <b>Universe</b> — {esc(universe_name)}",
        f"◆ <b>Mode</b> — {mode_plain}",
        "",
        SECTION_SEPARATOR,
        "",
        f"<b>{p1_mention}</b> {score_badge} <b>{p2_mention}</b>",
        "",
        outcome_line,
        "",
        SECTION_SEPARATOR,
        "",
    ]

    for m in res.matchups:
        role_title = m.role.title()
        c1_raw = chars[m.player_1.character_id].name if m.player_1.character_id in chars else m.player_1.character_id
        c2_raw = chars[m.player_2.character_id].name if m.player_2.character_id in chars else m.player_2.character_id
        c1_name = c1_raw if len(c1_raw) <= 48 else c1_raw[:47] + "…"
        c2_name = c2_raw if len(c2_raw) <= 48 else c2_raw[:47] + "…"
        s1 = m.player_1.score
        s2 = m.player_2.score
        if m.winner is MatchupWinner.PLAYER_1:
            role_hdr = f"<b>✦ {esc(role_title)}</b>"
            matchup_line = f"<b>〔{esc(c1_name)} · {s1}〕</b> — {esc(c2_name)} · {s2}"
        elif m.winner is MatchupWinner.PLAYER_2:
            role_hdr = f"<b>✦ {esc(role_title)}</b>"
            matchup_line = f"{esc(c1_name)} · {s1} — <b>〔{esc(c2_name)} · {s2}〕</b>"
        else:
            role_hdr = f"<b>✦ {esc(role_title)}</b> · {STATUS_DRAW}"
            matchup_line = f"{esc(c1_name)} · {s1} — {esc(c2_name)} · {s2}"
        lines.extend([role_hdr, matchup_line, ""])

    lines.extend(
        [
            SECTION_SEPARATOR,
            "",
            f"<b>{to_bold_serif_upper('TEAM SCORES')}</b>",
            "",
            f"▪ {p1_mention} — <b>{summary.total_player_1}/700</b>",
            f"▪ {p2_mention} — <b>{summary.total_player_2}/700</b>",
            "",
            explanation,
        ]
    )
    return clamp_text("\n".join(lines))


def render_detailed_result_page(
    match: ManagedMatch,
    *,
    role_index: int = 0,
    player_names: Mapping[str, str],
    char_lookup: Mapping[str, CharacterEntry] | None = None,
) -> str:
    """Screen 11 — Battle Breakdown (all 7 roles in one message, NO emojis)."""
    outcome = match.outcome
    if outcome is None or outcome.resolution is None:
        return clamp_text(
            f"<b>{to_bold_serif_upper('BATTLE BREAKDOWN')}</b>\n\nDetailed role matchups are unavailable for early-terminated matches."
        )

    res = outcome.resolution
    summary = res.summary
    chars = char_lookup or {}
    p1_id, p2_id = match.players
    p1_mention = format_user_mention(p1_id, player_names.get(p1_id))
    p2_mention = format_user_mention(p2_id, player_names.get(p2_id))

    lines = [
        f"<b>{to_bold_serif_upper('BATTLE BREAKDOWN')}</b>",
        "",
        f"<b>{p1_mention}</b> 〔{summary.wins_player_1} — {summary.wins_player_2}〕 <b>{p2_mention}</b>",
        "",
        SECTION_SEPARATOR,
        "",
        "<i>Power / Role Fit / Score</i>",
        "",
    ]

    for m in res.matchups:
        role_title = m.role.title()
        c1_raw = chars[m.player_1.character_id].name if m.player_1.character_id in chars else m.player_1.character_id
        c2_raw = chars[m.player_2.character_id].name if m.player_2.character_id in chars else m.player_2.character_id
        c1_name = c1_raw if len(c1_raw) <= 48 else c1_raw[:47] + "…"
        c2_name = c2_raw if len(c2_raw) <= 48 else c2_raw[:47] + "…"
        s1_disp = f"<b>〔{m.player_1.score}〕</b>" if m.winner is MatchupWinner.PLAYER_1 else str(m.player_1.score)
        s2_disp = f"<b>〔{m.player_2.score}〕</b>" if m.winner is MatchupWinner.PLAYER_2 else str(m.player_2.score)
        role_hdr = (
            f"◆ <b>{esc(role_title)}</b> ┊ {STATUS_DRAW}"
            if m.winner is MatchupWinner.DRAW
            else f"◆ <b>{esc(role_title)}</b>"
        )
        lines.extend(
            [
                role_hdr,
                f"▪ {esc(c1_name)} — {m.player_1.power} / {m.player_1.fit} / {s1_disp}",
                f"▪ {esc(c2_name)} — {m.player_2.power} / {m.player_2.fit} / {s2_disp}",
                "",
            ]
        )

    lines.extend(
        [
            SECTION_SEPARATOR,
            "",
            f"<b>Total Score — {summary.total_player_1} : {summary.total_player_2}</b>",
        ]
    )
    return clamp_text("\n".join(lines))


# ---------------------------------------------------------------------------
# /game, /list, /profile, /leaderboard, /history
# ---------------------------------------------------------------------------


def render_active_game(
    match: ManagedMatch,
    *,
    requester_id: str,
    universe_name: str,
    player_names: Mapping[str, str],
    group_title: str | None = None,
    group_link: str | None = None,
) -> str:
    p1_id, p2_id = match.players
    p1_mention = format_user_mention(p1_id, player_names.get(p1_id))
    p2_mention = format_user_mention(p2_id, player_names.get(p2_id))
    f1 = sum(1 for role in ROLE_ORDER if match.public_view.teams[p1_id].get(role) is not None)
    f2 = sum(1 for role in ROLE_ORDER if match.public_view.teams[p2_id].get(role) is not None)
    active_id = match.draft_snapshot.active_player_id
    in_timeout = match.inactivity_claim_offered_to is not None

    def _turn_tag(pid: str) -> str:
        if active_id != pid:
            return ""
        return f" ✦ {STATUS_TIMEOUT}" if in_timeout else f" ✦ {STATUS_CURRENT_TURN}"

    u_icon = universe_icon(match.universe_id)
    safe_group = esc(group_title) if group_title else "Original Group"
    group_display = f'<a href="{esc(group_link)}">{safe_group}</a>' if group_link else safe_group
    status_text = (
        "Turn expired — awaiting opponent decision"
        if in_timeout
        else "Drafting in progress"
    )

    return clamp_text(
        "\n".join(
            [
                f"<b>⚔️ {to_bold_serif_upper('ACTIVE MATCH')}</b>",
                "",
                f"◆ <b>Universe</b> — {u_icon} {esc(universe_name)}",
                f"◆ <b>Mode</b> — {format_mode_label(match.game_mode)}",
                "",
                SECTION_SEPARATOR,
                "",
                f"🔵 <b>{p1_mention}</b> 〔{f1}/7〕{_turn_tag(p1_id)}",
                "",
                f"🔴 <b>{p2_mention}</b> 〔{f2}/7〕{_turn_tag(p2_id)}",
                "",
                SECTION_SEPARATOR,
                "",
                f"▪ <b>Group:</b> {group_display}",
                f"▪ <b>Status:</b> {status_text}",
            ]
        )
    )


def render_recover_confirmation() -> str:
    return clamp_text(
        "\n".join(
            [
                f"<b>🔄 {to_bold_serif_upper('RECOVER MATCH')}</b>",
                "",
                "Unable to access your ongoing match?",
                "",
                "Recover the gameplay messages in the original group.",
                "",
                SECTION_SEPARATOR,
                "",
                "<i>Your characters, assignments, skips and turn timer will remain unchanged.</i>",
            ]
        )
    )


def render_recover_success(
    *,
    group_title: str | None = None,
    group_link: str | None = None,
) -> str:
    safe_group = esc(group_title) if group_title else "Original Group"
    group_display = f'<a href="{esc(group_link)}">{safe_group}</a>' if group_link else safe_group
    return clamp_text(
        "\n".join(
            [
                f"<b>✅ {to_bold_serif_upper('MATCH RECOVERED')}</b>",
                "",
                "Your gameplay messages have been restored.",
                "",
                f"◆ <b>Group</b> — {group_display}",
                "",
                "<i>Continue playing where you left off.</i>",
            ]
        )
    )


def render_recover_failed() -> str:
    return clamp_text(
        "\n".join(
            [
                f"<b>⚠️ {to_bold_serif_upper('RECOVERY INCOMPLETE')}</b>",
                "",
                "We could not restore both gameplay messages in the original group.",
                "",
                "Use /game to try again.",
            ]
        )
    )


def render_no_active_game() -> str:
    return clamp_text(
        "\n".join(
            [
                f"<b>⚔️ {to_bold_serif_upper('NO ACTIVE MATCH')}</b>",
                "",
                "You don't have an ongoing battle.",
                "",
                "Use /arena in a group to challenge another player.",
                "",
                "<i>Your next battle awaits.</i>",
            ]
        )
    )


def render_forfeit_confirmation(
    *,
    requester_id: str = "",
    requester_name: str = "Player",
    opponent_id: str = "",
    opponent_name: str = "Opponent",
) -> str:
    req_mention = format_user_mention(requester_id, requester_name)
    opp_mention = format_user_mention(opponent_id, opponent_name)
    return clamp_text(
        "\n".join(
            [
                f"<b>{to_bold_serif_upper('CONFIRM SURRENDER')}</b>",
                "",
                f"{req_mention}, are you sure you want to forfeit against {opp_mention}?",
                "",
                SECTION_SEPARATOR,
                "",
                "<i>Forfeiting will immediately end the match in your opponent's favour.</i>",
            ]
        )
    )


def render_catalogue_universes(universes: Sequence[Universe]) -> str:
    if not universes:
        return clamp_text("📚 <b>Character Catalogue</b>\n\nNo active universes with published datasets are available yet.")
    return clamp_text(
        "\n".join(
            [
                "📚 <b>Character Catalogue</b>",
                "",
                "Select a universe to browse its published playable characters.",
            ]
        )
    )


def render_catalogue_page(
    *,
    universe: Universe,
    rarity_filter: str,
    characters: Sequence[CharacterEntry],
    page: int,
    total_pages: int,
) -> str:
    """Render public catalogue. NEVER exposes Power, Fits, scores, or RP."""
    u_icon = universe_icon(universe.universe_id)
    filter_label = "All" if rarity_filter == "all" else rarity_filter
    lines = [
        "📚 <b>Character Catalogue</b>",
        "",
        f"{u_icon} {esc(universe.name)}",
        "",
        f"Filter: <b>{esc(filter_label)}</b>",
        "",
    ]
    if not characters:
        lines.append("No published characters match this filter.")
    else:
        for ch in characters:
            lines.append(f"{rarity_icon(ch.rarity)} {esc(ch.name)}")
        lines.append("")
        lines.append(f"Page {page + 1}/{total_pages}")
    return clamp_text("\n".join(lines))


def render_profile(profile: PlayerProfileView | None, *, fallback_name: str) -> str:
    if profile is None:
        return clamp_text(
            "\n".join(
                [
                    f"👤 <b>{esc(fallback_name)}</b>",
                    "",
                    "Competitive profiles, universal ratings, and match statistics are not yet available.",
                    "They will unlock with the Competitive Progression update (Module 8).",
                ]
            )
        )
    return clamp_text(
        "\n".join(
            [
                f"👤 <b>{esc(profile.display_name)}</b>",
                f"Rank: <b>{esc(profile.rank_name)}</b> ({profile.rating})",
                "",
                f"Matches: {profile.matches_played} ({profile.wins}W / {profile.losses}L / {profile.draws}D)",
                f"Win Rate: {profile.win_rate_pct:.1f}%",
                f"Current Streak: {esc(profile.current_streak)}",
                f"Recent Form: {esc(profile.recent_form)}",
                "",
                f"Friendly Matches: {profile.friendly_matches} ({profile.friendly_wins}W)",
            ]
        )
    )


def render_leaderboard(
    entries: Sequence[LeaderboardEntryView],
    *,
    scope: str,
    requester_position: int | None,
    available: bool,
) -> str:
    title = "🏆 <b>Leaderboard — Global</b>" if scope == "g" else "🏆 <b>Leaderboard — This Group</b>"
    if not available:
        return clamp_text(
            "\n".join(
                [
                    title,
                    "",
                    "Competitive leaderboards are not yet available.",
                    "Universal ratings and rankings will arrive in Module 8.",
                ]
            )
        )
    if not entries:
        return clamp_text(f"{title}\n\nNo ranked entries recorded yet.")

    lines = [title, ""]
    for row in entries:
        lines.append(f"{row.position}. {esc(row.display_name)} — <b>{row.rating}</b>")
    if requester_position is not None:
        lines.append("")
        lines.append(f"Your position: #{requester_position}")
    return clamp_text("\n".join(lines))


def render_history(entries: Sequence[MatchHistoryEntryView], *, available: bool) -> str:
    if not available:
        return clamp_text(
            "\n".join(
                [
                    "📜 <b>Match History</b>",
                    "",
                    "Persistent match history is not yet available.",
                    "Match logs will arrive with Persistence & Competitive Progression (Modules 7–8).",
                ]
            )
        )
    if not entries:
        return clamp_text("📜 <b>Match History</b>\n\nNo completed matches yet.")
    lines = ["📜 <b>Match History</b>", ""]
    for item in entries:
        lines.append(
            f"• <code>#{esc(item.match_id)}</code> — {esc(item.universe_name)} ({esc(item.game_mode)}) vs {esc(item.opponent_name)}: <b>{esc(item.outcome_label)}</b>"
        )
    return clamp_text("\n".join(lines))


# ---------------------------------------------------------------------------
# Player Profile 2.0 (Screens 01-05 & Historical Battle Breakdown)
# ---------------------------------------------------------------------------


def render_profile_text_fallback(
    *,
    player_id: str,
    player_name: str,
    stats: PlayerStatsSummary,
) -> str:
    """Compact text fallback if Player Card PNG generation fails."""
    mention = format_user_mention(player_id, player_name)
    rate_str = f"{stats.win_rate_pct:.1f}%" if stats.win_rate_pct is not None else "—"
    return clamp_text(
        "\n".join(
            [
                f"<b>⚔️ {to_bold_serif_upper('KAYI ARENA')}</b>",
                "",
                f"◆ <b>Player:</b> {mention}",
                f"◆ <b>Ranked Battles:</b> {stats.battles_played}",
                "",
                f"▸ <b>Victories:</b> {stats.victories}",
                f"▸ <b>Defeats:</b> {stats.defeats}",
                f"▸ <b>Draws:</b> {stats.draws}",
                f"▸ <b>Win rate:</b> {rate_str}",
            ]
        )
    )


def render_profile_statistics(
    *,
    player_id: str,
    player_name: str,
    universe_label: str,
    game_mode: str,
    stats: PlayerStatsSummary,
) -> str:
    mention = format_user_mention(player_id, player_name)
    mode_label = "Ranked" if game_mode == "ranked" else "Friendly"
    rate_str = f"{stats.win_rate_pct:.2f}%" if stats.win_rate_pct is not None else "—"
    if stats.current_streak == 0:
        streak_str = "0"
    elif stats.current_streak == 1:
        streak_str = "1 win"
    else:
        streak_str = f"{stats.current_streak} wins"
    avg_str = f"{stats.avg_team_score}/700" if stats.avg_team_score is not None else "—"
    high_str = f"{stats.highest_team_score}/700" if stats.highest_team_score is not None else "—"

    return clamp_text(
        "\n".join(
            [
                f"<b>📊 {to_bold_serif_upper('PLAYER STATISTICS')}</b>",
                "",
                f"◆ <b>Player:</b> {mention}",
                f"◆ <b>Universe:</b> {esc(universe_label)}",
                f"◆ <b>Mode:</b> {mode_label}",
                "",
                SECTION_SEPARATOR,
                "",
                f"<b>{to_bold_serif_upper('BATTLE RECORD')}</b>",
                "",
                f"▸ <b>Battles played:</b> {stats.battles_played}",
                f"▸ <b>Victories:</b> {stats.victories}",
                f"▸ <b>Defeats:</b> {stats.defeats}",
                f"▸ <b>Draws:</b> {stats.draws}",
                f"▸ <b>Win rate:</b> {rate_str}",
                "",
                SECTION_SEPARATOR,
                "",
                f"<b>{to_bold_serif_upper('PERFORMANCE')}</b>",
                "",
                f"▸ <b>Current streak:</b> {streak_str}",
                f"▸ <b>Best win streak:</b> {stats.best_streak}",
                f"▸ <b>Average team score:</b> {avg_str}",
                f"▸ <b>Highest team score:</b> {high_str}",
            ]
        )
    )


def render_profile_universe_selection(
    *,
    player_id: str,
    player_name: str,
    selected_label: str,
    game_mode: str,
    origin: str,
) -> str:
    mention = format_user_mention(player_id, player_name)
    noun = "match history" if origin == "history" else "battle statistics"
    return clamp_text(
        "\n".join(
            [
                f"<b>🌐 {to_bold_serif_upper('SELECT UNIVERSE')}</b>",
                "",
                f"Choose a universe to view {mention}'s {noun}.",
                "",
                SECTION_SEPARATOR,
                "",
                f"◆ <b>Selected:</b> {esc(selected_label)}",
                f"◆ <b>Mode:</b> {format_mode_label(game_mode)}",
            ]
        )
    )


def _history_reason_short(rec: HistoricalMatchRecord) -> str:
    return {
        MatchOutcomeReason.NORMAL_MATCHUP_COUNT: "role wins",
        MatchOutcomeReason.NORMAL_COMBINED_SCORE: "total score",
        MatchOutcomeReason.NORMAL_DRAW: "draw",
        MatchOutcomeReason.VOLUNTARY_FORFEITURE: "forfeit",
        MatchOutcomeReason.INACTIVITY_VICTORY: "inactivity",
    }.get(rec.outcome_reason, rec.outcome_reason.value.replace("_", " "))


def render_profile_history(
    *,
    player_id: str,
    player_name: str,
    universe_id: str,
    universe_label: str,
    game_mode: str,
    records: Sequence[HistoricalMatchRecord],
    player_names: Mapping[str, str],
) -> str:
    mention = format_user_mention(player_id, player_name)
    u_icon = "🌐" if universe_id == "all" else universe_icon(universe_id)

    lines = [
        f"<b>{to_bold_serif_upper('MATCH HISTORY')}</b>",
        "",
        f"✦ <b>{mention}</b>",
        "",
        f"{u_icon} <b>{esc(universe_label)}</b> · {format_mode_label(game_mode)}",
        "",
        SECTION_SEPARATOR,
        "",
    ]
    if not records:
        lines.append("No battles found for this selection.")
        return clamp_text("\n".join(lines))

    last_date_str = ""
    for idx, rec in enumerate(records, start=1):
        dt = datetime.fromtimestamp(float(rec.completed_at), tz=_IST)
        date_str = to_small_caps_digits(dt.strftime("%d %B %Y"))
        if date_str != last_date_str:
            if last_date_str:
                lines.append("")
            lines.extend([date_str, ""])
            last_date_str = date_str
        else:
            lines.append("")

        opp_id = rec.player_2_id if rec.player_1_id == player_id else rec.player_1_id
        opp_mention = format_user_mention(opp_id, player_names.get(opp_id))
        m_icon = universe_icon(rec.universe_id)

        if rec.winner_id == player_id:
            outcome_dot = "🟢"
        elif rec.winner_id is not None:
            outcome_dot = "🔴"
        else:
            outcome_dot = "⚪"

        score_badge = ""
        if rec.outcome.resolution is not None and rec.wins_player_1 is not None and rec.wins_player_2 is not None:
            owner_w = rec.wins_player_1 if rec.player_1_id == player_id else rec.wins_player_2
            opp_w = rec.wins_player_2 if rec.player_1_id == player_id else rec.wins_player_1
            score_badge = f" 〔{to_bold_serif_upper(str(owner_w))} — {to_bold_serif_upper(str(opp_w))}〕"

        time_str = to_small_caps_digits(dt.strftime("%I:%M %p"))
        reason_str = to_small_caps_digits(_history_reason_short(rec))
        num_str = to_bold_serif_upper(f"{idx:02d}")
        lines.append(f"{outcome_dot} <b>{num_str}.</b> {m_icon} <b>{opp_mention}</b>{score_badge}")
        lines.append(f"{time_str} · {reason_str}")

    lines.extend(
        [
            "",
            SECTION_SEPARATOR,
            "",
            f"🟢 {STATUS_VICTORY} · 🔴 {STATUS_DEFEAT} · ⚪ {STATUS_DRAW}",
        ]
    )
    return clamp_text("\n".join(lines))


def _format_hist_duration(seconds: float | None) -> str | None:
    if seconds is None:
        return None
    secs = max(0, int(round(seconds)))
    hours, rem = divmod(secs, 3600)
    mins, s = divmod(rem, 60)
    if hours > 0:
        return f"{hours}h {mins}m {s}s"
    if mins > 0:
        return f"{mins}m {s}s"
    return f"{s}s"


def render_historical_match_details(
    rec: HistoricalMatchRecord,
    *,
    universe_name: str,
    player_names: Mapping[str, str],
    char_lookup: Mapping[str, CharacterEntry],
    duration_seconds: float | None = None,
) -> str:
    """Screen 05 — Historical Match Details preserving original blue/red player order."""
    p1_id, p2_id = rec.player_1_id, rec.player_2_id
    p1_mention = format_user_mention(p1_id, player_names.get(p1_id))
    p2_mention = format_user_mention(p2_id, player_names.get(p2_id))
    mode_plain = "Ranked" if rec.game_mode == "ranked" else "Friendly"
    dur_str = _format_hist_duration(duration_seconds)
    dt = datetime.fromtimestamp(float(rec.completed_at), tz=_IST)
    ts_str = to_small_caps_digits(dt.strftime("%d %b %Y · %I:%M %p IST"))

    header_lines = [
        f"<b>{to_bold_serif_upper('BATTLE RECORD')}</b>",
        "",
        f"◆ <b>Universe</b> — {esc(universe_name)}",
        f"◆ <b>Mode</b> — {mode_plain}",
    ]
    if dur_str is not None:
        header_lines.append(f"◆ <b>Duration</b> — {dur_str}")
    header_lines.extend(["", SECTION_SEPARATOR, ""])

    res = rec.outcome.resolution
    if res is None:
        if rec.outcome.reason is MatchOutcomeReason.VOLUNTARY_FORFEITURE:
            winner_id = rec.winner_id or ""
            forfeiter_id = rec.outcome.forfeiting_player_id or ""
            winner_m = format_user_mention(winner_id, player_names.get(winner_id))
            forfeiter_m = format_user_mention(forfeiter_id, player_names.get(forfeiter_id))
            body = [
                f"🟢 <b>{winner_m}</b> 〔{STATUS_VICTORY}〕",
                "",
                f"🔴 <b>{forfeiter_m}</b> 〔{STATUS_DEFEAT}〕",
                "",
                SECTION_SEPARATOR,
                "",
                "▪ <b>Reason:</b> Forfeit",
                "",
                f"<i>{forfeiter_m} surrendered the match.</i>",
            ]
        elif rec.outcome.reason is MatchOutcomeReason.INACTIVITY_VICTORY:
            winner_id = rec.winner_id or ""
            inactive_id = rec.outcome.inactive_player_id or ""
            winner_m = format_user_mention(winner_id, player_names.get(winner_id))
            inactive_m = format_user_mention(inactive_id, player_names.get(inactive_id))
            body = [
                f"🟢 <b>{winner_m}</b> 〔{STATUS_VICTORY}〕",
                "",
                f"🔴 <b>{inactive_m}</b> 〔{STATUS_DEFEAT}〕",
                "",
                SECTION_SEPARATOR,
                "",
                "▪ <b>Reason:</b> Turn timeout",
                "",
                "<i>Victory claimed by the opponent.</i>",
            ]
        else:
            body = [
                f"🔵 <b>{p1_mention}</b>",
                "",
                f"🔴 <b>{p2_mention}</b>",
                "",
                SECTION_SEPARATOR,
                "",
                f"▪ <b>Result:</b> {esc(rec.status.value)}",
            ]
        return clamp_text("\n".join([*header_lines, *body, "", ts_str]))

    summary = res.summary
    score_badge = f"〔{to_bold_serif_upper(str(summary.wins_player_1))} — {to_bold_serif_upper(str(summary.wins_player_2))}〕"
    if res.outcome is MatchOutcome.PLAYER_1_WIN:
        outcome_line = f"✦ <b>{p1_mention}</b> — {STATUS_VICTORY}"
        winner_mention = p1_mention
    elif res.outcome is MatchOutcome.PLAYER_2_WIN:
        outcome_line = f"✦ <b>{p2_mention}</b> — {STATUS_VICTORY}"
        winner_mention = p2_mention
    else:
        outcome_line = f"✦ <b>{to_bold_serif_upper('BATTLE DRAW')}</b>"
        winner_mention = ""

    if res.decided_by is DecidedBy.MATCHUP_COUNT:
        explanation = "<i>Victory by role wins.</i>"
    elif res.decided_by is DecidedBy.COMBINED_SCORE:
        explanation = f"<i>Both players won an equal number of roles. {winner_mention} wins by a higher total team score.</i>"
    else:
        explanation = "<i>Both players finished with equal role wins and equal team scores.</i>"

    lines = [
        *header_lines,
        f"<b>{p1_mention}</b> {score_badge} <b>{p2_mention}</b>",
        "",
        outcome_line,
        "",
        SECTION_SEPARATOR,
        "",
    ]

    for m in res.matchups:
        role_title = m.role.title()
        raw_c1 = char_lookup[m.player_1.character_id].name if m.player_1.character_id in char_lookup else m.player_1.character_id
        raw_c2 = char_lookup[m.player_2.character_id].name if m.player_2.character_id in char_lookup else m.player_2.character_id
        c1_name = raw_c1 if len(raw_c1) <= 64 else f"{raw_c1[:63].rstrip()}…"
        c2_name = raw_c2 if len(raw_c2) <= 64 else f"{raw_c2[:63].rstrip()}…"
        s1 = m.player_1.score
        s2 = m.player_2.score
        if m.winner is MatchupWinner.PLAYER_1:
            role_hdr = f"<b>✦ {esc(role_title)}</b>"
            matchup_line = f"<b>〔{esc(c1_name)} · {s1}〕</b> — {esc(c2_name)} · {s2}"
        elif m.winner is MatchupWinner.PLAYER_2:
            role_hdr = f"<b>✦ {esc(role_title)}</b>"
            matchup_line = f"{esc(c1_name)} · {s1} — <b>〔{esc(c2_name)} · {s2}〕</b>"
        else:
            role_hdr = f"<b>✦ {esc(role_title)}</b> · {STATUS_DRAW}"
            matchup_line = f"{esc(c1_name)} · {s1} — {esc(c2_name)} · {s2}"
        lines.extend([role_hdr, matchup_line, ""])

    lines.extend(
        [
            SECTION_SEPARATOR,
            "",
            f"<b>{to_bold_serif_upper('TEAM SCORES')}</b>",
            "",
            f"▸ {p1_mention} — <b>{summary.total_player_1}/700</b>",
            f"▸ {p2_mention} — <b>{summary.total_player_2}/700</b>",
            "",
            explanation,
            "",
            ts_str,
        ]
    )
    rendered = "\n".join(lines)
    if len(rendered) <= 4096:
        return rendered
    # Preserve complete HTML lines if a message ever exceeds Telegram's 4096-char cap.
    kept: list[str] = []
    total_len = 0
    for line in lines:
        add_len = len(line) + (1 if kept else 0)
        if total_len + add_len > 4096:
            break
        kept.append(line)
        total_len += add_len
    return "\n".join(kept)


def render_historical_battle_breakdown(
    rec: HistoricalMatchRecord,
    *,
    player_names: Mapping[str, str],
    char_lookup: Mapping[str, CharacterEntry],
) -> str:
    res = rec.outcome.resolution
    if res is None:
        return clamp_text(
            f"<b>{to_bold_serif_upper('BATTLE BREAKDOWN')}</b>\n\nDetailed role matchups are unavailable for this match."
        )
    summary = res.summary
    p1_mention = format_user_mention(rec.player_1_id, player_names.get(rec.player_1_id))
    p2_mention = format_user_mention(rec.player_2_id, player_names.get(rec.player_2_id))

    lines = [
        f"<b>{to_bold_serif_upper('BATTLE BREAKDOWN')}</b>",
        "",
        f"<b>{p1_mention}</b> 〔{summary.wins_player_1} — {summary.wins_player_2}〕 <b>{p2_mention}</b>",
        "",
        SECTION_SEPARATOR,
        "",
        "<i>Power / Role Fit / Score</i>",
        "",
    ]
    for m in res.matchups:
        role_title = m.role.title()
        c1_raw = char_lookup[m.player_1.character_id].name if m.player_1.character_id in char_lookup else m.player_1.character_id
        c2_raw = char_lookup[m.player_2.character_id].name if m.player_2.character_id in char_lookup else m.player_2.character_id
        c1_name = c1_raw if len(c1_raw) <= 48 else c1_raw[:47] + "…"
        c2_name = c2_raw if len(c2_raw) <= 48 else c2_raw[:47] + "…"
        s1_disp = f"<b>〔{m.player_1.score}〕</b>" if m.winner is MatchupWinner.PLAYER_1 else str(m.player_1.score)
        s2_disp = f"<b>〔{m.player_2.score}〕</b>" if m.winner is MatchupWinner.PLAYER_2 else str(m.player_2.score)
        role_hdr = (
            f"◆ <b>{esc(role_title)}</b> ┊ {STATUS_DRAW}"
            if m.winner is MatchupWinner.DRAW
            else f"◆ <b>{esc(role_title)}</b>"
        )
        lines.extend(
            [
                role_hdr,
                f"▸ {esc(c1_name)} — {m.player_1.power} / {m.player_1.fit} / {s1_disp}",
                f"▸ {esc(c2_name)} — {m.player_2.power} / {m.player_2.fit} / {s2_disp}",
                "",
            ]
        )
    lines.extend(
        [
            SECTION_SEPARATOR,
            "",
            f"<b>Total Score — {summary.total_player_1} : {summary.total_player_2}</b>",
        ]
    )
    return clamp_text("\n".join(lines))
