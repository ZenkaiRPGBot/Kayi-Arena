"""Native Telegram inline keyboard builders for Kayi Arena.

Uses official Bot API `style` values ("primary", "success", "danger") and
standard default buttons without arbitrary hex colors.
"""

from __future__ import annotations

from typing import Mapping, Sequence

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.database import Universe
from app.matches import ChallengeRecord, ChallengeStatus, ManagedMatch
from app.telegram.callbacks import encode_cb, rarity_to_code, role_to_index
from app.telegram.config import BotConfig
from app.telegram.constants import (
    RARITY_ICONS,
    ROLE_ORDER,
    STYLE_DANGER,
    STYLE_PRIMARY,
    STYLE_SUCCESS,
    UNIVERSES_PER_PAGE,
    rarity_icon,
    role_label,
    universe_icon,
)


def _btn(
    text: str,
    *,
    callback_data: str | None = None,
    url: str | None = None,
    style: str | None = None,
) -> InlineKeyboardButton:
    kwargs: dict[str, object] = {"text": text}
    if callback_data is not None:
        kwargs["callback_data"] = callback_data
    if url is not None:
        kwargs["url"] = url
    if style is not None:
        kwargs["style"] = style
    return InlineKeyboardButton(**kwargs)


def build_home_keyboard(config: BotConfig) -> InlineKeyboardMarkup:
    add_group_url = f"https://t.me/{config.bot_username}?startgroup=true"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [_btn("➕ Add to Group", url=add_group_url, style=STYLE_SUCCESS)],
            [
                _btn("📢 Updates", url=config.updates_url, style=STYLE_PRIMARY),
                _btn("💬 Support", callback_data=encode_cb("sup", "menu"), style=STYLE_PRIMARY),
            ],
            [_btn("👨💻 Developer", url=config.developer_url, style=STYLE_DANGER)],
        ]
    )


def build_support_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                _btn("🐞 Report a Bug", callback_data=encode_cb("sup", "bug"), style=STYLE_DANGER),
                _btn("💡 Suggest an Idea", callback_data=encode_cb("sup", "idea"), style=STYLE_SUCCESS),
            ],
            [_btn("« Back", callback_data=encode_cb("home"))],
        ]
    )


def build_universe_selection_keyboard(
    *,
    universes: Sequence[Universe],
    page: int,
    game_mode: str,
) -> InlineKeyboardMarkup:
    if not universes:
        return InlineKeyboardMarkup(
            inline_keyboard=[[_btn("« Back", callback_data=encode_cb("home"))]]
        )

    total_pages = max(1, (len(universes) + UNIVERSES_PER_PAGE - 1) // UNIVERSES_PER_PAGE)
    safe_page = max(0, min(page, total_pages - 1))
    start = safe_page * UNIVERSES_PER_PAGE
    chunk = universes[start : start + UNIVERSES_PER_PAGE]
    mode_code = "r" if game_mode == "ranked" else "f"

    rows: list[list[InlineKeyboardButton]] = []
    for i in range(0, len(chunk), 2):
        row = []
        for u in chunk[i : i + 2]:
            icon = universe_icon(u.universe_id)
            row.append(
                _btn(
                    f"{icon} {u.name}",
                    callback_data=encode_cb("u", safe_page, mode_code, u.universe_id),
                )
            )
        rows.append(row)

    if total_pages > 1:
        nav: list[InlineKeyboardButton] = []
        if safe_page > 0:
            nav.append(_btn("‹", callback_data=encode_cb("um", safe_page - 1, mode_code)))
        nav.append(_btn(f"{safe_page + 1}/{total_pages}", callback_data=encode_cb("noop")))
        if safe_page + 1 < total_pages:
            nav.append(_btn("›", callback_data=encode_cb("um", safe_page + 1, mode_code)))
        rows.append(nav)

    rows.append(
        [
            _btn(
                "🎲 Random Universe",
                callback_data=encode_cb("u", safe_page, mode_code, "rand"),
                style=STYLE_PRIMARY,
            )
        ]
    )

    ranked_label = "✓ Ranked" if game_mode == "ranked" else "Ranked"
    friendly_label = "✓ Friendly" if game_mode == "friendly" else "Friendly"
    rows.append(
        [
            _btn(
                ranked_label,
                callback_data=encode_cb("um", safe_page, "r"),
                style=STYLE_PRIMARY if game_mode == "ranked" else None,
            ),
            _btn(
                friendly_label,
                callback_data=encode_cb("um", safe_page, "f"),
                style=STYLE_PRIMARY if game_mode == "friendly" else None,
            ),
        ]
    )
    rows.append([_btn("« Back", callback_data=encode_cb("home"))])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_challenge_keyboard(challenge: ChallengeRecord) -> InlineKeyboardMarkup | None:
    if challenge.status is not ChallengeStatus.OPEN:
        return None
    switch_label = "🤝 Friendly" if challenge.game_mode == "ranked" else "🏆 Ranked"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                _btn(
                    "⚔️ Accept Challenge",
                    callback_data=encode_cb("ca", challenge.challenge_id, challenge.generation),
                    style=STYLE_SUCCESS,
                )
            ],
            [
                _btn(
                    switch_label,
                    callback_data=encode_cb("cm", challenge.challenge_id, challenge.generation),
                ),
                _btn(
                    "✖ Cancel",
                    callback_data=encode_cb("cx", challenge.challenge_id, challenge.generation),
                    style=STYLE_DANGER,
                ),
            ],
        ]
    )


def build_draft_board_keyboard(match: ManagedMatch) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [_btn("ℹ️ Match Information", callback_data=encode_cb("mi", match.match_id))]
        ]
    )


def build_awaiting_shuffle_keyboard(match: ManagedMatch) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                _btn(
                    "🎲 Shuffle",
                    callback_data=encode_cb("sh", match.match_id, match.generation),
                    style=STYLE_PRIMARY,
                )
            ]
        ]
    )


def build_character_revealed_keyboard(match: ManagedMatch) -> InlineKeyboardMarkup:
    active_id = match.draft_snapshot.active_player_id or ""
    roster = match.public_view.teams.get(active_id, {})
    open_roles = [role for role in ROLE_ORDER if roster.get(role) is None]

    rows: list[list[InlineKeyboardButton]] = []
    for i in range(0, len(open_roles), 2):
        pair = open_roles[i : i + 2]
        rows.append(
            [
                _btn(
                    role_label(role),
                    callback_data=encode_cb(
                        "as", match.match_id, match.generation, role_to_index(role)
                    ),
                    style=STYLE_SUCCESS,
                )
                for role in pair
            ]
        )

    skips_left = match.public_view.skips_remaining.get(active_id, 0)
    if skips_left > 0:
        rows.append(
            [
                _btn(
                    f"⏭ Skip ({skips_left}/2)",
                    callback_data=encode_cb("sk", match.match_id, match.generation),
                )
            ]
        )

    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_inactivity_keyboard(match: ManagedMatch) -> InlineKeyboardMarkup:
    inactive_id = match.draft_snapshot.active_player_id or ""
    rows: list[list[InlineKeyboardButton]] = [
        [
            _btn(
                "🏆 Claim Victory",
                callback_data=encode_cb("cv", match.match_id, match.generation),
                style=STYLE_SUCCESS,
            )
        ]
    ]
    if match.extensions_remaining.get(inactive_id, 0) > 0:
        rows.append(
            [
                _btn(
                    "⏳ Grant 60 More Seconds",
                    callback_data=encode_cb("ex", match.match_id, match.generation),
                    style=STYLE_PRIMARY,
                )
            ]
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_match_results_keyboard(
    match: ManagedMatch,
    *,
    player_names: Mapping[str, str],
) -> InlineKeyboardMarkup:
    p1_id, p2_id = match.players
    p1_name = player_names.get(p1_id, p1_id)[:20]
    p2_name = player_names.get(p2_id, p2_id)[:20]
    rows: list[list[InlineKeyboardButton]] = [
        [
            _btn(
                "🔁 Rematch",
                callback_data=encode_cb("rm", match.match_id),
                style=STYLE_SUCCESS,
            )
        ]
    ]
    if match.outcome and match.outcome.resolution is not None:
        rows.append(
            [
                _btn(
                    "📊 Detailed Results",
                    callback_data=encode_cb("dr", match.match_id, 0),
                )
            ]
        )
    rows.append(
        [
            _btn(f"👤 {p1_name}", callback_data=encode_cb("pr", p1_id)),
            _btn(f"👤 {p2_name}", callback_data=encode_cb("pr", p2_id)),
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_detailed_results_keyboard(match_id: str, role_index: int) -> InlineKeyboardMarkup:
    nav: list[InlineKeyboardButton] = []
    if role_index > 0:
        nav.append(_btn("‹ Previous", callback_data=encode_cb("dr", match_id, role_index - 1)))
    nav.append(_btn(f"{role_index + 1}/7", callback_data=encode_cb("noop")))
    if role_index < 6:
        nav.append(_btn("Next ›", callback_data=encode_cb("dr", match_id, role_index + 1)))

    return InlineKeyboardMarkup(
        inline_keyboard=[
            nav,
            [_btn("« Back to Results", callback_data=encode_cb("mr", match_id))],
        ]
    )


def build_active_game_keyboard(
    match: ManagedMatch,
    *,
    game_link: str | None = None,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if game_link:
        rows.append([_btn("🎯 Go to Game", url=game_link, style=STYLE_PRIMARY)])
    else:
        rows.append(
            [
                _btn(
                    "🎯 Go to Game",
                    callback_data=encode_cb("gg", match.match_id),
                    style=STYLE_PRIMARY,
                )
            ]
        )
    rows.append([_btn("🔄 Recover Game", callback_data=encode_cb("gg", match.match_id))])
    rows.append(
        [
            _btn(
                "🏳️ Forfeit Match",
                callback_data=encode_cb("gf", match.match_id, match.generation),
                style=STYLE_DANGER,
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_no_active_game_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [_btn("⚔️ Enter Arena", callback_data=encode_cb("arena"), style=STYLE_PRIMARY)]
        ]
    )


def build_forfeit_confirm_keyboard(match: ManagedMatch) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                _btn(
                    "Yes, Forfeit",
                    callback_data=encode_cb("gfc", match.match_id, match.generation),
                    style=STYLE_DANGER,
                ),
                _btn(
                    "Cancel",
                    callback_data=encode_cb("gfk", match.match_id, match.generation),
                ),
            ]
        ]
    )


def build_catalogue_universes_keyboard(universes: Sequence[Universe]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for i in range(0, len(universes), 2):
        rows.append(
            [
                _btn(
                    f"{universe_icon(u.universe_id)} {u.name}",
                    callback_data=encode_cb("ls", u.universe_id, "a", 0),
                )
                for u in universes[i : i + 2]
            ]
        )
    rows.append([_btn("« Back to Home", callback_data=encode_cb("home"))])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_catalogue_page_keyboard(
    *,
    universe_id: str,
    rarity_filter: str,
    page: int,
    total_pages: int,
) -> InlineKeyboardMarkup:
    def _filter_btn(label: str, key: str) -> InlineKeyboardButton:
        selected = rarity_filter == key
        text = f"✓ {label}" if selected else label
        return _btn(
            text,
            callback_data=encode_cb("ls", universe_id, rarity_to_code(key), 0),
            style=STYLE_PRIMARY if selected else None,
        )

    rows: list[list[InlineKeyboardButton]] = [
        [_filter_btn("All", "all"), _filter_btn(f"{rarity_icon('Legendary')} Legendary", "Legendary")],
        [
            _filter_btn(f"{rarity_icon('Epic')} Epic", "Epic"),
            _filter_btn(f"{rarity_icon('Rare')} Rare", "Rare"),
        ],
        [
            _filter_btn(f"{rarity_icon('Uncommon')} Uncommon", "Uncommon"),
            _filter_btn(f"{rarity_icon('Common')} Common", "Common"),
        ],
    ]
    r_code = rarity_to_code(rarity_filter)
    nav: list[InlineKeyboardButton] = []
    if page > 0:
        nav.append(_btn("‹", callback_data=encode_cb("ls", universe_id, r_code, page - 1)))
    nav.append(_btn(f"{page + 1}/{total_pages}", callback_data=encode_cb("noop")))
    if page + 1 < total_pages:
        nav.append(_btn("›", callback_data=encode_cb("ls", universe_id, r_code, page + 1)))
    rows.append(nav)
    rows.append([_btn("« Universes", callback_data=encode_cb("ls", "menu", "a", 0))])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_help_keyboard(topic: str = "menu") -> InlineKeyboardMarkup:
    if topic == "menu" or topic not in {"1", "2", "3", "4", "5", "6"}:
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    _btn("1", callback_data=encode_cb("hlp", "1"), style=STYLE_PRIMARY),
                    _btn("2", callback_data=encode_cb("hlp", "2"), style=STYLE_PRIMARY),
                    _btn("3", callback_data=encode_cb("hlp", "3"), style=STYLE_PRIMARY),
                ],
                [
                    _btn("4", callback_data=encode_cb("hlp", "4"), style=STYLE_PRIMARY),
                    _btn("5", callback_data=encode_cb("hlp", "5"), style=STYLE_PRIMARY),
                    _btn("6", callback_data=encode_cb("hlp", "6"), style=STYLE_PRIMARY),
                ],
            ]
        )

    chapter_num = int(topic)
    row: list[InlineKeyboardButton] = []
    if chapter_num > 1:
        row.append(_btn("← Previous", callback_data=encode_cb("hlp", str(chapter_num - 1))))
    row.append(_btn("☰", callback_data=encode_cb("hlp", "menu"), style=STYLE_SUCCESS))
    if chapter_num < 6:
        row.append(_btn("Next →", callback_data=encode_cb("hlp", str(chapter_num + 1)), style=STYLE_PRIMARY))
    return InlineKeyboardMarkup(inline_keyboard=[row])


def build_leaderboard_keyboard(
    *,
    scope: str,
    page: int,
    total_pages: int,
    available: bool,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = [
        [
            _btn(
                "🌍 Global" if scope != "g" else "✓ Global",
                callback_data=encode_cb("lb", "g", 0),
                style=STYLE_PRIMARY if scope == "g" else None,
            ),
            _btn(
                "👥 This Group" if scope != "c" else "✓ This Group",
                callback_data=encode_cb("lb", "c", 0),
                style=STYLE_PRIMARY if scope == "c" else None,
            ),
        ]
    ]
    if available:
        nav: list[InlineKeyboardButton] = []
        if page > 0:
            nav.append(_btn("‹", callback_data=encode_cb("lb", scope, page - 1)))
        nav.append(_btn(f"{page + 1}/{total_pages}", callback_data=encode_cb("noop")))
        if page + 1 < total_pages:
            nav.append(_btn("›", callback_data=encode_cb("lb", scope, page + 1)))
        rows.append(nav)
        rows.append([_btn("🔄 Refresh", callback_data=encode_cb("lb", scope, page))])
    rows.append([_btn("« Back to Home", callback_data=encode_cb("home"))])
    return InlineKeyboardMarkup(inline_keyboard=rows)
