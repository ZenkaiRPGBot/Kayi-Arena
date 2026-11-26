"""HTML presentation formatters for Kayi Arena Telegram UI.

All user-controlled strings are escaped via `html.escape`.
Messages are bounded to Telegram's 4096-char limit and photo captions to 1024 chars.
"""

from __future__ import annotations

import html
from typing import Mapping, Sequence

from app.database import CharacterEntry, Universe
from app.matches import (
    ChallengeRecord,
    ChallengeStatus,
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
    rarity_icon,
    role_label,
    universe_icon,
)
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
                "To challenge someone directly, reply to their message with /arena.",
                "",
                "To invite anyone in the group to play, send /arena without replying to a message.",
                "",
                "Select an anime universe and wait for your opponent to accept the challenge.",
                "",
                "Once accepted, the game begins!",
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


def render_challenge_card(
    challenge: ChallengeRecord,
    *,
    universe_name: str,
    challenger_name: str,
    target_name: str | None = None,
    seconds_remaining: float = 300.0,
) -> str:
    u_icon = universe_icon(challenge.universe_id)
    opponent_line = (
        f"Opponent: <b>{esc(target_name)}</b> (Direct Challenge)"
        if target_name
        else "Opponent: Waiting for a challenger..."
    )

    if challenge.status is ChallengeStatus.CANCELLED:
        status_block = "✖ <b>Challenge Cancelled</b>"
    elif challenge.status is ChallengeStatus.EXPIRED:
        status_block = "⌛ <b>Challenge Expired</b>"
    elif challenge.status is ChallengeStatus.ACCEPTED:
        status_block = "✅ <b>Challenge Accepted</b> — Match started!"
    else:
        status_block = f"Expires in: {format_duration_short(seconds_remaining)}\n\nWho will enter the arena?"

    return clamp_text(
        "\n".join(
            [
                "⚔️ <b>ARENA CHALLENGE</b>",
                "",
                f"Challenger: <b>{esc(challenger_name)}</b>",
                opponent_line,
                f"Universe: {u_icon} {esc(universe_name)}",
                f"Mode: {format_mode_label(challenge.game_mode)}",
                "Format: 1v1 • 7 Roles",
                status_block,
                "",
                f"Challenge <code>#{esc(challenge.challenge_id)}</code>",
            ]
        )
    )


# ---------------------------------------------------------------------------
# Draft Board & Character Cards
# ---------------------------------------------------------------------------


def _render_player_roster(
    *,
    marker: str,
    player_name: str,
    assignments: Mapping[str, str | None],
    skips_remaining: int,
    char_lookup: Mapping[str, CharacterEntry],
) -> list[str]:
    filled = sum(1 for role in ROLE_ORDER if assignments.get(role) is not None)
    lines = [f"{marker} <b>{esc(player_name)}</b> — {filled}/7", ""]
    for role in ROLE_ORDER:
        cid = assignments.get(role)
        if cid is None:
            lines.append(f"{role_label(role)}: —")
        else:
            rec = char_lookup.get(cid)
            if rec is not None:
                r_icon = rarity_icon(rec.rarity)
                lines.append(f"{role_label(role)}: {r_icon} {esc(rec.name)}")
            else:
                lines.append(f"{role_label(role)}: {esc(cid)}")
    lines.append("")
    lines.append(f"Skips remaining: {skips_remaining}/2")
    return lines


def render_draft_board(
    match: ManagedMatch,
    *,
    universe_name: str,
    player_names: Mapping[str, str],
    char_lookup: Mapping[str, CharacterEntry],
    seconds_remaining: float,
    last_action_line: str | None = None,
) -> str:
    p1_id, p2_id = match.players
    p1_name = player_names.get(p1_id, p1_id)
    p2_name = player_names.get(p2_id, p2_id)
    pv = match.public_view
    u_icon = universe_icon(match.universe_id)

    total_filled = sum(
        1
        for pid in (p1_id, p2_id)
        for role in ROLE_ORDER
        if pv.teams[pid].get(role) is not None
    )

    lines = [
        "⚔️ <b>KAYI ARENA</b>",
        "",
        f"{u_icon} {esc(universe_name)} • {format_mode_label(match.game_mode)}",
        f"Match <code>#{esc(match.match_id)}</code>",
        "",
        f"Draft progress: {total_filled}/14",
        "",
    ]
    lines.extend(
        _render_player_roster(
            marker="🔵",
            player_name=p1_name,
            assignments=pv.teams[p1_id],
            skips_remaining=pv.skips_remaining[p1_id],
            char_lookup=char_lookup,
        )
    )
    lines.append("")
    lines.extend(
        _render_player_roster(
            marker="🔴",
            player_name=p2_name,
            assignments=pv.teams[p2_id],
            skips_remaining=pv.skips_remaining[p2_id],
            char_lookup=char_lookup,
        )
    )
    lines.append("")
    if pv.active_player_id is not None:
        active_name = player_names.get(pv.active_player_id, pv.active_player_id)
        lines.append(f"🎯 <b>{esc(active_name)}'s turn</b>")
        lines.append(f"⏳ Turn deadline: {format_deadline_countdown(seconds_remaining)}")
    if last_action_line:
        lines.append("")
        lines.append(f"<i>{esc(last_action_line)}</i>")

    return clamp_text("\n".join(lines))


def render_awaiting_shuffle_card(
    match: ManagedMatch,
    *,
    player_names: Mapping[str, str],
) -> str:
    active_id = match.draft_snapshot.active_player_id or ""
    active_name = player_names.get(active_id, active_id)
    return clamp_caption(
        "\n".join(
            [
                "🎴 <b>Your next character</b>",
                "",
                f"{esc(active_name)}, it's your turn.",
                "",
                "Shuffle to reveal a random character.",
            ]
        )
    )


def render_revealed_character_card(
    match: ManagedMatch,
    *,
    character: CharacterEntry,
    universe_name: str,
    player_names: Mapping[str, str],
) -> str:
    """Render revealed character caption. NEVER exposes Power, Fits, scores, or RP."""
    active_id = match.draft_snapshot.active_player_id or ""
    active_name = player_names.get(active_id, active_id)
    skips = match.public_view.skips_remaining.get(active_id, 0)
    u_icon = universe_icon(match.universe_id)
    r_icon = rarity_icon(character.rarity)

    return clamp_caption(
        "\n".join(
            [
                f"<b>{esc(character.name)}</b>",
                "",
                f"{r_icon} {esc(character.rarity.upper())}",
                "",
                f"{u_icon} {esc(universe_name)}",
                "",
                f"🎯 {esc(active_name)}, choose a role.",
                "",
                f"Skips available: {skips}/2",
            ]
        )
    )


def render_turn_expired_card(
    match: ManagedMatch,
    *,
    player_names: Mapping[str, str],
) -> str:
    inactive_id = match.draft_snapshot.active_player_id or ""
    opponent_id = match.inactivity_claim_offered_to or ""
    inactive_name = player_names.get(inactive_id, inactive_id)
    opponent_name = player_names.get(opponent_id, opponent_id)

    return clamp_caption(
        "\n".join(
            [
                "⌛ <b>TURN EXPIRED</b>",
                "",
                f"{esc(inactive_name)} failed to complete the turn within the allocated time.",
                "",
                f"{esc(opponent_name)}, what would you like to do?",
                "",
                f"Respond within {int(match.timeout_policy.claim_window_seconds)} seconds.",
            ]
        )
    )


def render_retired_card_text(match: ManagedMatch, *, player_names: Mapping[str, str]) -> str:
    if match.status is MatchLifecycleStatus.COMPLETED and match.outcome and match.outcome.winner_id:
        w_name = player_names.get(match.outcome.winner_id, match.outcome.winner_id)
        return clamp_caption(f"🏁 <b>Draft Complete</b> — 🏆 {esc(w_name)} wins!")
    if match.status is MatchLifecycleStatus.COMPLETED:
        return clamp_caption("🏁 <b>Draft Complete</b> — 🤝 Match ended in a draw.")
    if match.status is MatchLifecycleStatus.FORFEITED:
        return clamp_caption("🏳️ <b>Match Forfeited</b>")
    if match.status is MatchLifecycleStatus.INACTIVITY_WIN:
        return clamp_caption("⌛ <b>Match Ended by Inactivity</b>")
    if match.status is MatchLifecycleStatus.ABANDONED:
        return clamp_caption("⌛ <b>Match Abandoned</b> — Mutual inactivity.")
    return clamp_caption("🏁 <b>Match Ended</b>")


# ---------------------------------------------------------------------------
# Match Results & Detailed Results
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
    mode_text = "Ranked Battle" if match.game_mode == "ranked" else "Friendly Battle"
    p1_id, p2_id = match.players
    p1_name = player_names.get(p1_id, p1_id)
    p2_name = player_names.get(p2_id, p2_id)
    chars = char_lookup or {}

    if outcome is None:
        return clamp_text(f"⚔️ Match <code>#{esc(match.match_id)}</code> — {esc(match.status.value)}")

    # Early / non-normal outcomes must NEVER invent 7 matchups or scores.
    if outcome.resolution is None:
        if outcome.reason is MatchOutcomeReason.VOLUNTARY_FORFEITURE:
            winner_name = player_names.get(outcome.winner_id or "", outcome.winner_id or "")
            forfeiter_name = player_names.get(
                outcome.forfeiting_player_id or "", outcome.forfeiting_player_id or ""
            )
            header = f"🏳️ <b>{esc(winner_name).upper()} WINS BY FORFEIT!</b>"
            detail = f"{esc(forfeiter_name)} forfeited the match."
        elif outcome.reason is MatchOutcomeReason.INACTIVITY_VICTORY:
            winner_name = player_names.get(outcome.winner_id or "", outcome.winner_id or "")
            inactive_name = player_names.get(
                outcome.inactive_player_id or "", outcome.inactive_player_id or ""
            )
            header = f"🏆 <b>{esc(winner_name).upper()} WINS BY INACTIVITY!</b>"
            detail = f"{esc(inactive_name)} failed to complete their turn in time."
        elif outcome.reason is MatchOutcomeReason.MUTUAL_INACTIVITY_ABANDONMENT:
            header = "⌛ <b>MATCH ABANDONED</b>"
            detail = "Mutual inactivity — no winner declared and no rating change."
        else:
            header = "🛑 <b>MATCH TERMINATED</b>"
            detail = "The match ended without resolution."

        return clamp_text(
            "\n".join(
                [
                    header,
                    "",
                    f"{u_icon} {esc(universe_name)} • {mode_text}",
                    f"Match <code>#{esc(match.match_id)}</code>",
                    "",
                    detail,
                ]
            )
        )

    res = outcome.resolution
    summary = res.summary
    if res.outcome is MatchOutcome.PLAYER_1_WIN:
        headline = f"🏆 <b>{esc(p1_name).upper()} WINS!</b>"
    elif res.outcome is MatchOutcome.PLAYER_2_WIN:
        headline = f"🏆 <b>{esc(p2_name).upper()} WINS!</b>"
    else:
        headline = "🤝 <b>MATCH DRAW!</b>"

    if res.decided_by is DecidedBy.MATCHUP_COUNT:
        decided_line = "Victory by role wins"
    elif res.decided_by is DecidedBy.COMBINED_SCORE:
        decided_line = (
            f"Victory by combined score ({summary.total_player_1} — {summary.total_player_2})"
        )
    else:
        decided_line = (
            f"Exact tie ({summary.total_player_1} — {summary.total_player_2})"
        )

    lines = [
        headline,
        "",
        f"{u_icon} {esc(universe_name)} • {mode_text}",
        "",
        f"<b>{esc(p1_name)}</b> {summary.wins_player_1} — {summary.wins_player_2} <b>{esc(p2_name)}</b>",
        "",
        f"{summary.draws} drawn {'matchup' if summary.draws == 1 else 'matchups'}",
        decided_line,
        f"Combined Score: {summary.total_player_1} — {summary.total_player_2}",
        "",
    ]

    for m in res.matchups:
        role_title = m.role.title()
        r_icon = ROLE_ICONS.get(role_title, "🎭")
        c1_name = chars[m.player_1.character_id].name if m.player_1.character_id in chars else m.player_1.character_id
        c2_name = chars[m.player_2.character_id].name if m.player_2.character_id in chars else m.player_2.character_id
        if m.winner is MatchupWinner.PLAYER_1:
            win_line = f"🔵 {esc(p1_name)} wins"
        elif m.winner is MatchupWinner.PLAYER_2:
            win_line = f"🔴 {esc(p2_name)} wins"
        else:
            win_line = "⚪ Draw"
        lines.extend(
            [
                f"{r_icon} <b>{esc(role_title)}</b>",
                f"{esc(c1_name)} {m.player_1.score} — {m.player_2.score} {esc(c2_name)}",
                win_line,
                "",
            ]
        )

    return clamp_text("\n".join(lines).rstrip())


def render_detailed_result_page(
    match: ManagedMatch,
    *,
    role_index: int,
    player_names: Mapping[str, str],
    char_lookup: Mapping[str, CharacterEntry] | None = None,
) -> str:
    """Paginated matchup detail: reveals ONLY Power and assigned-role Fit."""
    outcome = match.outcome
    if outcome is None or outcome.resolution is None:
        return clamp_text("📊 <b>Matchup Details</b>\n\nDetailed role matchups are unavailable for early-terminated matches.")

    chars = char_lookup or {}
    matchups = outcome.resolution.matchups
    idx = max(0, min(role_index, len(matchups) - 1))
    m = matchups[idx]
    p1_id, p2_id = match.players
    p1_name = player_names.get(p1_id, p1_id)
    p2_name = player_names.get(p2_id, p2_id)
    role_title = m.role.title()
    r_icon = ROLE_ICONS.get(role_title, "🎭")
    c1_name = chars[m.player_1.character_id].name if m.player_1.character_id in chars else m.player_1.character_id
    c2_name = chars[m.player_2.character_id].name if m.player_2.character_id in chars else m.player_2.character_id

    p1_badge = " ✓ Winner" if m.winner is MatchupWinner.PLAYER_1 else ""
    p2_badge = " ✓ Winner" if m.winner is MatchupWinner.PLAYER_2 else ""
    diff = abs(m.player_1.score - m.player_2.score)

    return clamp_text(
        "\n".join(
            [
                "📊 <b>Matchup Details</b>",
                "",
                f"{r_icon} <b>{esc(role_title)}</b>",
                "",
                f"<b>{esc(c1_name)}</b> — {esc(p1_name)}",
                "",
                f"Power: {m.player_1.power}/5",
                f"{esc(role_title)} Fit: {m.player_1.fit}/5",
                f"<b>{m.player_1.score}/100</b>{p1_badge}",
                "",
                f"<b>{esc(c2_name)}</b> — {esc(p2_name)}",
                "",
                f"Power: {m.player_2.power}/5",
                f"{esc(role_title)} Fit: {m.player_2.fit}/5",
                f"<b>{m.player_2.score}/100</b>{p2_badge}",
                "",
                f"Score difference: {diff}",
            ]
        )
    )


# ---------------------------------------------------------------------------
# /game, /list, /profile, /leaderboard, /history
# ---------------------------------------------------------------------------


def render_active_game(
    match: ManagedMatch,
    *,
    requester_id: str,
    universe_name: str,
    player_names: Mapping[str, str],
) -> str:
    p1_id, p2_id = match.players
    opp_id = p2_id if requester_id == p1_id else p1_id
    opp_name = player_names.get(opp_id, opp_id)
    active_id = match.draft_snapshot.active_player_id or ""
    active_name = player_names.get(active_id, active_id)
    u_icon = universe_icon(match.universe_id)
    filled = sum(
        1
        for pid in (p1_id, p2_id)
        for role in ROLE_ORDER
        if match.public_view.teams[pid].get(role) is not None
    )

    return clamp_text(
        "\n".join(
            [
                "🎮 <b>Your Active Match</b>",
                "",
                f"Opponent: <b>{esc(opp_name)}</b>",
                f"Universe: {u_icon} {esc(universe_name)}",
                f"Mode: {'Ranked' if match.game_mode == 'ranked' else 'Friendly'}",
                f"Progress: {filled}/14 characters",
                f"Current turn: <b>{esc(active_name)}</b>",
                "",
                "● Match in progress",
                "",
                f"Match <code>#{esc(match.match_id)}</code>",
            ]
        )
    )


def render_no_active_game() -> str:
    return clamp_text("You don't have an active match.")


def render_forfeit_confirmation() -> str:
    return clamp_text(
        "\n".join(
            [
                "⚠️ <b>Forfeit match?</b>",
                "",
                "Your opponent will be declared the winner.",
                "",
                "This action cannot be undone.",
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
