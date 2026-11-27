"""Error codes and exceptions for Module 4A (Database Foundation)."""

from __future__ import annotations

from enum import Enum


class DatabaseErrorCode(str, Enum):
    UNIVERSE_NOT_FOUND = "UNIVERSE_NOT_FOUND"
    UNIVERSE_EXISTS = "UNIVERSE_EXISTS"
    UNIVERSE_INACTIVE = "UNIVERSE_INACTIVE"
    INVALID_UNIVERSE_CONFIG = "INVALID_UNIVERSE_CONFIG"
    CHARACTER_NOT_FOUND = "CHARACTER_NOT_FOUND"
    CHARACTER_EXISTS = "CHARACTER_EXISTS"
    INVALID_CHARACTER = "INVALID_CHARACTER"
    INVALID_RARITY = "INVALID_RARITY"
    INVALID_TRANSITION = "INVALID_TRANSITION"
    PUBLICATION_BLOCKED = "PUBLICATION_BLOCKED"
    INVALID_IMPORT_FORMAT = "INVALID_IMPORT_FORMAT"
    VERSION_EXISTS = "VERSION_EXISTS"
    VERSION_NOT_FOUND = "VERSION_NOT_FOUND"
    INTEGRITY_FAILURE = "INTEGRITY_FAILURE"


class DatabaseError(ValueError):
    """Structured persistence/database error."""

    def __init__(self, code: DatabaseErrorCode, message: str) -> None:
        super().__init__(f"{code.value}: {message}")
        self.code = code
        self.message = message
