"""Compact, length-validated callback data encoding for Kayi Arena."""

from __future__ import annotations

from dataclasses import dataclass

from app.telegram.constants import MAX_CALLBACK_DATA_BYTES, ROLE_ORDER

_PREFIX = "ka"

_RARITY_TO_CODE = {
    "all": "a",
    "Legendary": "l",
    "Epic": "e",
    "Rare": "r",
    "Uncommon": "u",
    "Common": "c",
}
_CODE_TO_RARITY = {v: k for k, v in _RARITY_TO_CODE.items()}


@dataclass(frozen=True, slots=True)
class ParsedCallback:
    """Decoded callback payload."""

    action: str
    args: tuple[str, ...] = ()


def encode_cb(action: str, *parts: str | int) -> str:
    """Encode a callback payload and enforce Telegram's 64-byte UTF-8 limit."""
    tokens = [_PREFIX, action, *(str(p) for p in parts)]
    payload = ":".join(tokens)
    encoded = payload.encode("utf-8")
    if len(encoded) > MAX_CALLBACK_DATA_BYTES:
        raise ValueError(
            f"Callback data exceeds {MAX_CALLBACK_DATA_BYTES} bytes ({len(encoded)}): {payload!r}"
        )
    return payload


def decode_cb(data: str | None) -> ParsedCallback | None:
    """Parse a `ka:...` callback payload, returning None if malformed."""
    if not data or not isinstance(data, str):
        return None
    if len(data.encode("utf-8")) > MAX_CALLBACK_DATA_BYTES:
        return None
    parts = data.split(":")
    if len(parts) < 2 or parts[0] != _PREFIX or not parts[1]:
        return None
    return ParsedCallback(action=parts[1], args=tuple(parts[2:]))


def role_to_index(role: str) -> int:
    return ROLE_ORDER.index(role)


def index_to_role(idx_str: str) -> str | None:
    try:
        idx = int(idx_str)
    except ValueError:
        return None
    if 0 <= idx < len(ROLE_ORDER):
        return ROLE_ORDER[idx]
    return None


def rarity_to_code(rarity: str) -> str:
    return _RARITY_TO_CODE.get(rarity, "a")


def code_to_rarity(code: str) -> str:
    return _CODE_TO_RARITY.get(code, "all")
