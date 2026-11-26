"""Kayi Arena — Module 3: Match Resolution public API."""

from app.resolution.adapter import (
    ENGINE_TO_SCORING_ROLE,
    build_resolve_request_from_completed_draft,
    resolve_completed_draft,
)
from app.resolution.engine import (
    DatasetReader,
    RepositoryDatasetReader,
    resolve_match,
)
from app.resolution.errors import DatasetUnavailableError, ResolutionErrorCode
from app.resolution.invariants import (
    ResolutionInvariantError,
    validate_resolution_invariants,
)
from app.resolution.models import (
    DecidedBy,
    MatchOutcome,
    MatchResolutionFailure,
    MatchResolutionSuccess,
    MatchupParticipant,
    MatchupWinner,
    PLAYER_SLOTS,
    RESOLUTION_VERSION,
    ResolutionSummary,
    ResolveRequest,
    RoleMatchup,
    SUPPORTED_SCORING_VERSIONS,
    VALID_GAME_MODES,
    canonical_bytes,
    canonical_json,
)

__all__ = [
    "DatasetReader",
    "DatasetUnavailableError",
    "DecidedBy",
    "ENGINE_TO_SCORING_ROLE",
    "MatchOutcome",
    "MatchResolutionFailure",
    "MatchResolutionSuccess",
    "MatchupParticipant",
    "MatchupWinner",
    "PLAYER_SLOTS",
    "RESOLUTION_VERSION",
    "RepositoryDatasetReader",
    "ResolutionErrorCode",
    "ResolutionInvariantError",
    "ResolutionSummary",
    "ResolveRequest",
    "RoleMatchup",
    "SUPPORTED_SCORING_VERSIONS",
    "VALID_GAME_MODES",
    "build_resolve_request_from_completed_draft",
    "canonical_bytes",
    "canonical_json",
    "resolve_completed_draft",
    "resolve_match",
    "validate_resolution_invariants",
]
