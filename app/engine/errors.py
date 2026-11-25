"""Error codes and configuration exceptions for the Core Drafting Engine."""

from __future__ import annotations

from enum import Enum


class ErrorCode(str, Enum):
    """Rejection codes defined by Module 1 Sections 4.3 and 7."""

    MATCH_NOT_ACTIVE = "MATCH_NOT_ACTIVE"
    UNKNOWN_PLAYER = "UNKNOWN_PLAYER"
    STALE_REVISION = "STALE_REVISION"
    NOT_YOUR_TURN = "NOT_YOUR_TURN"
    WRONG_PHASE = "WRONG_PHASE"
    NO_CHARACTER_DRAWN = "NO_CHARACTER_DRAWN"
    ROLE_OCCUPIED = "ROLE_OCCUPIED"
    INVALID_ROLE = "INVALID_ROLE"
    NO_SKIPS_REMAINING = "NO_SKIPS_REMAINING"
    SKIP_NOT_POSSIBLE = "SKIP_NOT_POSSIBLE"
    INVALID_REASON = "INVALID_REASON"


class EngineConfigError(ValueError):
    """Raised when draft configuration, pool catalog, or snapshot data is invalid."""
