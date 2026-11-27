"""Domain models for Module 5 (Challenge, Match Lifecycle, and Recovery Views)."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from app.engine import DraftSnapshot, ErrorCode as DraftErrorCode, PublicDraftView, TerminalRecord
from app.matches.errors import MatchManagementErrorCode
from app.resolution import MatchResolutionSuccess


class ChallengeType(str, Enum):
    DIRECT = "direct"
    OPEN = "open"


class ChallengeStatus(str, Enum):
    OPEN = "open"
    ACCEPTED = "accepted"
    DECLINED = "declined"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class MatchLifecycleStatus(str, Enum):
    DRAFTING = "drafting"
    COMPLETED = "completed"
    FORFEITED = "forfeited"
    INACTIVITY_WIN = "inactivity_win"
    ABANDONED = "abandoned"
    TERMINATED_ADMIN = "terminated_admin"
    TERMINATED_TECHNICAL = "terminated_technical"


class MatchOutcomeReason(str, Enum):
    NORMAL_MATCHUP_COUNT = "normal_matchup_count"
    NORMAL_COMBINED_SCORE = "normal_combined_score"
    NORMAL_DRAW = "normal_draw"
    VOLUNTARY_FORFEITURE = "voluntary_forfeiture"
    INACTIVITY_VICTORY = "inactivity_victory"
    MUTUAL_INACTIVITY_ABANDONMENT = "mutual_inactivity_abandonment"
    ADMINISTRATIVE_TERMINATION = "administrative_termination"
    TECHNICAL_TERMINATION = "technical_termination"


@dataclass(frozen=True, slots=True)
class TimeoutPolicy:
    """Configurable match timer settings (approved initial defaults, pinned per match)."""

    challenge_ttl_seconds: float = 300.0
    turn_timeout_seconds: float = 120.0
    claim_window_seconds: float = 60.0
    extension_seconds: float = 60.0
    extensions_per_player: int = 1
    allow_inactivity_claim: bool = True


ProvisionalTimeoutPolicy = TimeoutPolicy


@dataclass(frozen=True, slots=True)
class MessageReference:
    """Opaque UI message reference stored for future Module 6 /game retrieval."""

    chat_id: str
    message_id: str
    kind: str = "game"


@dataclass(frozen=True, slots=True)
class ChallengeRecord:
    """Immutable challenge state snapshot."""

    challenge_id: str
    challenge_type: ChallengeType
    challenger_id: str
    target_player_id: str | None
    universe_id: str
    game_mode: str
    chat_id: str
    status: ChallengeStatus
    created_at: float
    expires_at: float
    generation: int = 0
    accepted_by: str | None = None
    match_id: str | None = None


@dataclass(frozen=True, slots=True)
class MatchOutcomeSummary:
    """Distinct terminal outcome record (never fabricates scores on early termination)."""

    reason: MatchOutcomeReason
    winner_id: str | None
    loser_id: str | None
    affects_rating: bool
    forfeiting_player_id: str | None = None
    inactive_player_id: str | None = None
    resolution: MatchResolutionSuccess | None = None
    terminal_record: TerminalRecord | None = None


@dataclass(frozen=True, slots=True)
class ManagedMatch:
    """Complete managed match state integrating Modules 1, 3, and 4A."""

    match_id: str
    challenge_id: str
    players: tuple[str, str]
    universe_id: str
    game_mode: str
    dataset_version: str
    status: MatchLifecycleStatus
    draft_snapshot: DraftSnapshot
    public_view: PublicDraftView
    generation: int
    turn_started_at: float
    turn_deadline_at: float
    turn_number_at_start: int
    extensions_remaining: dict[str, int]
    timeout_policy: TimeoutPolicy
    created_at: float
    updated_at: float
    inactivity_claim_offered_to: str | None = None
    inactivity_claim_expires_at: float | None = None
    message_refs: tuple[MessageReference, ...] = ()
    outcome: MatchOutcomeSummary | None = None


@dataclass(frozen=True, slots=True)
class DraftCommandSelection:
    """Logical /draft command routing result for future Telegram integration."""

    action: str  # "list_universes" | "challenge_created"
    eligible_universes: tuple[str, ...] = ()
    challenge: ChallengeRecord | None = None


@dataclass(frozen=True, slots=True)
class ChallengeOperationResult:
    accepted: bool
    error_code: MatchManagementErrorCode | None = None
    message: str = ""
    challenge: ChallengeRecord | None = None
    match: ManagedMatch | None = None


@dataclass(frozen=True, slots=True)
class MatchOperationResult:
    accepted: bool
    error_code: MatchManagementErrorCode | None = None
    draft_error_code: DraftErrorCode | None = None
    message: str = ""
    match: ManagedMatch | None = None
    idempotent: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)
