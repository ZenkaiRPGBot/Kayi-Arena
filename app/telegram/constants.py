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

# UI 2.0 Textual symbols & separators
SECTION_SEPARATOR = "──────── ✦ ────────"

# UI 2.0 Small-caps status indicators
STATUS_CURRENT_TURN = "ᴄᴜʀʀᴇɴᴛ ᴛᴜʀɴ"
STATUS_SKIPPED = "sᴋɪᴘᴘᴇᴅ"
STATUS_VICTORY = "ᴠɪᴄᴛᴏʀʏ"
STATUS_DEFEAT = "ᴅᴇꜰᴇᴀᴛ"
STATUS_TIMEOUT = "ᴛɪᴍᴇᴏᴜᴛ"
STATUS_NO_RESPONSE = "ɴᴏ ʀᴇsᴘᴏɴsᴇ"
STATUS_DRAW = "ᴅʀᴀᴡ"

# Pagination defaults
UNIVERSES_PER_PAGE = 6
CATALOGUE_PER_PAGE = 8
LEADERBOARD_PER_PAGE = 10
RANDOM_UNIVERSE_ID = "random"


def to_bold_serif_upper(text: str) -> str:
    """Convert ASCII Latin letters and digits to Mathematical Bold Serif (preserving Unicode)."""
    out: list[str] = []
    for ch in text:
        code = ord(ch)
        if 0x41 <= code <= 0x5A:  # A-Z
            out.append(chr(0x1D400 + (code - 0x41)))
        elif 0x61 <= code <= 0x7A:  # a-z -> uppercase bold serif
            out.append(chr(0x1D400 + (code - 0x61)))
        elif 0x30 <= code <= 0x39:  # 0-9
            out.append(chr(0x1D7CE + (code - 0x30)))
        else:
            out.append(ch)
    return "".join(out)


def to_bold_sans(text: str) -> str:
    """Convert ASCII Latin letters and digits to Mathematical Bold Sans-Serif."""
    out: list[str] = []
    for ch in text:
        code = ord(ch)
        if 0x41 <= code <= 0x5A:  # A-Z
            out.append(chr(0x1D5D4 + (code - 0x41)))
        elif 0x61 <= code <= 0x7A:  # a-z
            out.append(chr(0x1D5EE + (code - 0x61)))
        elif 0x30 <= code <= 0x39:  # 0-9
            out.append(chr(0x1D7EC + (code - 0x30)))
        else:
            out.append(ch)
    return "".join(out)


def role_button_label(role: str) -> str:
    icon = ROLE_ICONS.get(role, "🎭")
    return f"{icon} {to_bold_sans(role)}"


_SMALL_CAPS_ALPHA = str.maketrans(
    "abcdefghijklmnopqrstuvwxyz",
    "ᴀʙᴄᴅᴇꜰɢʜɪᴊᴋʟᴍɴᴏᴘǫʀsᴛᴜᴠᴡxʏᴢ",
)


def to_small_caps_digits(text: str) -> str:
    """Convert ASCII lowercase/uppercase letters to small-caps and digits to monospace."""
    out: list[str] = []
    for ch in text.lower():
        code = ord(ch)
        if 0x30 <= code <= 0x39:
            out.append(chr(0x1D7F6 + (code - 0x30)))
        else:
            out.append(ch.translate(_SMALL_CAPS_ALPHA))
    return "".join(out)


def role_label(role: str) -> str:
    icon = ROLE_ICONS.get(role, "🎭")
    return f"{icon} {role}"


def rarity_icon(rarity: str) -> str:
    return RARITY_ICONS.get(rarity, "⚪")


def universe_icon(universe_id: str) -> str:
    key = universe_id.strip().lower()
    if key == RANDOM_UNIVERSE_ID:
        return "🎲"
    return UNIVERSE_ICONS.get(key, "🌐")
