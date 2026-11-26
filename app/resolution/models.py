"""Immutable request, matchup, result, and canonical JSON models for Module 3."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import Any, Mapping

from app.resolution.errors import ResolutionErrorCode
from app.scoring import SCORE_1_0_VERSION, SCORING_ROLES

RESOLUTION_VERSION = "RES-1.0"
SUPPORTED_SCORING_VERSIONS: frozenset[str] = frozenset({SCORE_1_0_VERSION})
VALID_GAME_MODES: frozenset[str] = frozenset({"ranked", "friendly"})
PLAYER_SLOTS: tuple[str, str] = ("player_1", "player_2")


class MatchOutcome(str, Enum):
    PLAYER_1_WIN = "player_1_win"
    PLAYER_2_WIN = "player_2_win"
    DRAW = "draw"


class DecidedBy(str, Enum):
    MATCHUP_COUNT = "matchup_count"
    COMBINED_SCORE = "combined_score"
    NONE = "none"


class MatchupWinner(str, Enum):
    PLAYER_1 = "player_1"
    PLAYER_2 = "player_2"
    DRAW = "draw"


def canonical_json(payload: Mapping[str, Any]) -> str:
    """Serialize to deterministic UTF-8 JSON (sorted keys, compact, no trailing newline).

    Uses ``ensure_ascii=False`` so Unicode strings serialize directly in UTF-8.
    Rejects NaN/Infinity via ``allow_nan=False``.
    """
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def canonical_bytes(payload: Mapping[str, Any]) -> bytes:
    """Return UTF-8 encoded canonical JSON bytes."""
    return canonical_json(payload).encode("utf-8")


@dataclass(frozen=True, slots=True)
class ResolveRequest:
    """Input contract for Module 3 match resolution."""

    match_id: str
    universe_id: str
    game_mode: str
    starting_player: str
    dataset_version: str
    players: Mapping[str, str]
    teams: Mapping[str, Mapping[str, str]]


@dataclass(frozen=True, slots=True)
class MatchupParticipant:
    """Assigned-role snapshot for one player's character in a single role matchup."""

    character_id: str
    power: int
    fit: int
    score: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "character_id": self.character_id,
            "power": self.power,
            "fit": self.fit,
            "score": self.score,
        }


@dataclass(frozen=True, slots=True)
class RoleMatchup:
    """Single same-role head-to-head comparison."""

    role: str
    player_1: MatchupParticipant
    player_2: MatchupParticipant
    winner: MatchupWinner
    margin: int  # player_1.score - player_2.score

    def to_dict(self) -> dict[str, Any]:
        return {
            "role": self.role,
            "player_1": self.player_1.to_dict(),
            "player_2": self.player_2.to_dict(),
            "winner": self.winner.value,
            "margin": self.margin,
        }


@dataclass(frozen=True, slots=True)
class ResolutionSummary:
    """Aggregate matchup wins, draws, and combined team totals."""

    wins_player_1: int
    wins_player_2: int
    draws: int
    total_player_1: int
    total_player_2: int
    total_margin: int  # total_player_1 - total_player_2

    def to_dict(self) -> dict[str, int]:
        return {
            "wins_player_1": self.wins_player_1,
            "wins_player_2": self.wins_player_2,
            "draws": self.draws,
            "total_player_1": self.total_player_1,
            "total_player_2": self.total_player_2,
            "total_margin": self.total_margin,
        }


@dataclass(frozen=True, slots=True)
class MatchResolutionSuccess:
    """Complete deterministic match resolution output."""

    resolution_version: str
    scoring_version: str
    dataset_version: str
    match_id: str
    universe_id: str
    game_mode: str
    starting_player: str
    players: Mapping[str, str]
    outcome: MatchOutcome
    decided_by: DecidedBy
    summary: ResolutionSummary
    matchups: tuple[RoleMatchup, ...]
    ok: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "players", MappingProxyType(dict(self.players)))

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": True,
            "resolution_version": self.resolution_version,
            "scoring_version": self.scoring_version,
            "dataset_version": self.dataset_version,
            "match_id": self.match_id,
            "universe_id": self.universe_id,
            "game_mode": self.game_mode,
            "starting_player": self.starting_player,
            "players": {slot: self.players[slot] for slot in PLAYER_SLOTS},
            "outcome": self.outcome.value,
            "decided_by": self.decided_by.value,
            "summary": self.summary.to_dict(),
            "matchups": [m.to_dict() for m in self.matchups],
        }

    def to_canonical_json(self) -> str:
        return canonical_json(self.to_dict())

    def to_canonical_bytes(self) -> bytes:
        return canonical_bytes(self.to_dict())


def _clean_details(details: Mapping[str, Any]) -> dict[str, Any]:
    """Strip None values recursively so canonical failure JSON never contains null."""
    cleaned: dict[str, Any] = {}
    for k, v in details.items():
        if v is None:
            continue
        if isinstance(v, Mapping):
            nested = _clean_details(v)
            if nested:
                cleaned[str(k)] = nested
        elif isinstance(v, (list, tuple)):
            cleaned[str(k)] = [item for item in v if item is not None]
        else:
            cleaned[str(k)] = v
    return cleaned


@dataclass(frozen=True, slots=True)
class MatchResolutionFailure:
    """Typed failure result with deterministic error code, message, and optional details."""

    error_code: ResolutionErrorCode
    message: str
    details: Mapping[str, Any] = field(default_factory=dict)
    ok: bool = False

    def __post_init__(self) -> None:
        cleaned = _clean_details(self.details)
        object.__setattr__(self, "details", MappingProxyType(cleaned))

    @property
    def retryable(self) -> bool:
        return self.error_code is ResolutionErrorCode.DATASET_UNAVAILABLE

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "ok": False,
            "error_code": self.error_code.value,
            "message": self.message,
        }
        if self.details:
            payload["details"] = dict(self.details)
        return payload

    def to_canonical_json(self) -> str:
        return canonical_json(self.to_dict())

    def to_canonical_bytes(self) -> bytes:
        return canonical_bytes(self.to_dict())
