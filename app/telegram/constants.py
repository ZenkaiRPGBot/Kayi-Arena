"""Permanent presentation constants, Telegram limits, and icons."""

from __future__ import annotations

from app.engine import ROLES

ROLE_ORDER: tuple[str, ...] = ROLES

ROLE_ICONS: dict[str, str] = {
    "Captain": "👑",
    "Strategist": "🧠",
    "Attacker": "⚔️",
    "Tank": "🛡️",
    "Assassin": "🗡️",
    "Support": "✨",
    "Healer": "💚",
}

RARITY_ICONS: dict[str, str] = {
    "Common": "⚪",
    "Uncommon": "🟢",
    "Rare": "🔵",
    "Epic": "🟣",
    "Legendary": "🟡",
}

UNIVERSE_ICONS: dict[str, str] = {
    "naruto": "🍥",
    "one_piece": "🏴‍☠️",
    "bleach": "🗡️",
    "dragon_ball": "🐉",
    "jujutsu_kaisen": "🤞",
    "demon_slayer": "🔥",
    "attack_on_titan": "🧱",
    "hunter_x_hunter": "🃏",
}

# Native Telegram Bot API button styles
STYLE_PRIMARY = "primary"
STYLE_SUCCESS = "success"
STYLE_DANGER = "danger"
STYLE_DEFAULT: str | None = None

# Telegram API limits
MAX_MESSAGE_LENGTH = 4096
MAX_CAPTION_LENGTH = 1024
MAX_CALLBACK_DATA_BYTES = 64

# Pagination defaults
UNIVERSES_PER_PAGE = 6
CATALOGUE_PER_PAGE = 8
LEADERBOARD_PER_PAGE = 10


def role_label(role: str) -> str:
    icon = ROLE_ICONS.get(role, "🎭")
    return f"{icon} {role}"


def rarity_icon(rarity: str) -> str:
    return RARITY_ICONS.get(rarity, "⚪")


def universe_icon(universe_id: str) -> str:
    return UNIVERSE_ICONS.get(universe_id.strip().lower(), "🌐")
