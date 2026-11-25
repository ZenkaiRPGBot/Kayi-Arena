"""Immutable data structures, state projections, and serialization for Module 1."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping

from app.engine.errors import ErrorCode

ROLES: tuple[str, ...] = (
    "Captain",
    "Strategist",
    "Attacker",
    "Tank",
    "Assassin",
    "Support",
    "Healer",
)

MIN_POOL_SIZE = 14
DEFAULT_SKIPS_PER_PLAYER = 2
TOTAL_ASSIGNMENTS = 14
MAX_ACCEPTED_DRAFT_ACTIONS = 36


class MatchStatus(str, Enum):
    ACTIVE = "ACTIVE"
    COMPLETED = "COMPLETED"
    TERMINATED = "TERMINATED"


class DraftPhase(str, Enum):
    AWAITING_SHUFFLE = "AWAITING_SHUFFLE"
    AWAITING_DECISION = "AWAITING_DECISION"


class TerminationReason(str, Enum):
    FORFEIT = "forfeit"
    INACTIVITY = "inactivity"
    BOTH_INACTIVE = "both_inactive"
    CANCELLED = "cancelled"
    ADMINISTRATIVE = "administrative"


@dataclass(frozen=True, slots=True)
class CatalogEntry:
    """Frozen character identifier and rarity tier (never includes ratings)."""

    character_id: str
    rarity_id: str

    def to_dict(self) -> dict[str, str]:
        return {"character_id": self.character_id, "rarity_id": self.rarity_id}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> CatalogEntry:
        return cls(
            character_id=str(data["character_id"]),
            rarity_id=str(data["rarity_id"]),
        )


@dataclass(frozen=True, slots=True)
class DraftConfigSnapshot:
    """Frozen match configuration snapshot captured at draft start."""

    rarity_weights: dict[str, float]
    skips_per_player: int = DEFAULT_SKIPS_PER_PLAYER
    roles: tuple[str, ...] = ROLES

    def to_dict(self) -> dict[str, Any]:
        return {
            "rarity_weights": {k: float(v) for k, v in sorted(self.rarity_weights.items())},
            "skips_per_player": int(self.skips_per_player),
            "roles": list(self.roles),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> DraftConfigSnapshot:
        return cls(
            rarity_weights={str(k): float(v) for k, v in dict(data["rarity_weights"]).items()},
            skips_per_player=int(data["skips_per_player"]),
            roles=tuple(str(r) for r in data["roles"]),
        )


@dataclass(frozen=True, slots=True)
class TerminalRecord:
    """Internal terminal metadata recorded on external termination."""

    reason: TerminationReason
    subject_player_id: str | None = None
    source_label: str = ""
    caller_reference: str = ""
    held_character_at_termination: CatalogEntry | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "reason": self.reason.value,
            "subject_player_id": self.subject_player_id,
            "source_label": self.source_label,
            "caller_reference": self.caller_reference,
            "held_character_at_termination": (
                self.held_character_at_termination.to_dict()
                if self.held_character_at_termination is not None
                else None
            ),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> TerminalRecord:
        held = data.get("held_character_at_termination")
        return cls(
            reason=TerminationReason(data["reason"]),
            subject_player_id=data.get("subject_player_id"),
            source_label=str(data.get("source_label", "")),
            caller_reference=str(data.get("caller_reference", "")),
            held_character_at_termination=(
                CatalogEntry.from_dict(held) if held is not None else None
            ),
        )


@dataclass(frozen=True, slots=True)
class PublicTerminalSummary:
    """Player-facing terminal summary (reason and optional subject player only)."""

    reason: TerminationReason
    subject_player_id: str | None = None


@dataclass(frozen=True, slots=True)
class DraftEvent:
    """Event emitted by an accepted engine action."""

    action: str
    actor_id: str | None
    revision: int
    character: CatalogEntry | None = None
    role: str | None = None
    reason: TerminationReason | None = None


@dataclass(frozen=True, slots=True)
class CompletedDraftOutput:
    """Handoff payload to Match Resolution (Module 3) on COMPLETED."""

    match_id: str
    universe_id: str
    mode: str
    starting_player_id: str
    dataset_version: str
    teams: dict[str, dict[str, str]]


@dataclass(frozen=True, slots=True)
class PublicDraftView:
    """Player-facing projection (Section 5.5). Never exposes pool, weights, or RNG."""

    match_id: str
    players: tuple[str, str]
    universe_id: str
    mode: str
    status: MatchStatus
    phase: DraftPhase | None
    revision: int
    active_player_id: str | None
    progress: int
    turn_number: int | None
    teams: dict[str, dict[str, str]]
    remaining_roles: dict[str, tuple[str, ...]]
    skips_remaining: dict[str, int]
    held_character: CatalogEntry | None
    can_skip: bool
    terminal_summary: PublicTerminalSummary | None


@dataclass(frozen=True, slots=True)
class DraftSnapshot:
    """Full serializable internal snapshot for persistence and restoration."""

    match_id: str
    players: tuple[str, str]
    universe_id: str
    mode: str
    config: DraftConfigSnapshot
    catalog: tuple[CatalogEntry, ...]
    dataset_version: str
    starting_player_id: str
    teams: dict[str, dict[str, str]]
    skips_remaining: dict[str, int]
    held_character: CatalogEntry | None
    last_skipped_id: str | None
    status: MatchStatus
    terminal_record: TerminalRecord | None
    revision: int
    timestamps: dict[str, Any] = field(default_factory=dict)

    @property
    def total_assignments(self) -> int:
        return sum(len(team) for team in self.teams.values())

    @property
    def active_player_id(self) -> str | None:
        if self.status is not MatchStatus.ACTIVE:
            return None
        p1, p2 = self.players
        other = p2 if self.starting_player_id == p1 else p1
        return self.starting_player_id if self.total_assignments % 2 == 0 else other

    @property
    def phase(self) -> DraftPhase | None:
        if self.status is not MatchStatus.ACTIVE:
            return None
        return (
            DraftPhase.AWAITING_DECISION
            if self.held_character is not None
            else DraftPhase.AWAITING_SHUFFLE
        )

    @property
    def turn_number(self) -> int | None:
        if self.status is not MatchStatus.ACTIVE:
            return None
        return self.total_assignments + 1

    def assigned_ids(self) -> set[str]:
        return {
            char_id
            for team in self.teams.values()
            for char_id in team.values()
        }

    def available_pool(self) -> tuple[CatalogEntry, ...]:
        """Catalog minus assigned characters minus currently held character."""
        excluded = self.assigned_ids()
        if self.held_character is not None:
            excluded.add(self.held_character.character_id)
        return tuple(c for c in self.catalog if c.character_id not in excluded)

    def eligible_pool(self) -> tuple[CatalogEntry, ...]:
        """Available pool minus last-skipped character (if set)."""
        excluded = self.assigned_ids()
        if self.held_character is not None:
            excluded.add(self.held_character.character_id)
        if self.last_skipped_id is not None:
            excluded.add(self.last_skipped_id)
        return tuple([c for c in self.catalog if c.character_id not in excluded])

    def can_skip(self) -> bool:
        """Whether the active player can legally skip the currently held character."""
        if self.status is not MatchStatus.ACTIVE or self.held_character is None:
            return False
        active = self.active_player_id
        if active is None or self.skips_remaining.get(active, 0) <= 0:
            return False
        return (len(self.catalog) - self.total_assignments - 1) > 0

    def remaining_roles(self) -> dict[str, tuple[str, ...]]:
        return {
            pid: tuple(role for role in self.config.roles if role not in self.teams[pid])
            for pid in self.players
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "match_id": self.match_id,
            "players": list(self.players),
            "universe_id": self.universe_id,
            "mode": self.mode,
            "config": self.config.to_dict(),
            "catalog": [c.to_dict() for c in self.catalog],
            "dataset_version": self.dataset_version,
            "starting_player_id": self.starting_player_id,
            "teams": {
                pid: {role: self.teams[pid][role] for role in sorted(self.teams[pid])}
                for pid in self.players
            },
            "skips_remaining": {pid: int(self.skips_remaining[pid]) for pid in self.players},
            "held_character": (
                self.held_character.to_dict() if self.held_character is not None else None
            ),
            "last_skipped_id": self.last_skipped_id,
            "status": self.status.value,
            "terminal_record": (
                self.terminal_record.to_dict() if self.terminal_record is not None else None
            ),
            "revision": int(self.revision),
            "timestamps": dict(self.timestamps),
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))

    def state_hash(self) -> str:
        return hashlib.sha256(self.to_json().encode("utf-8")).hexdigest()

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> DraftSnapshot:
        players_raw = data["players"]
        players = (str(players_raw[0]), str(players_raw[1]))
        held = data.get("held_character")
        term = data.get("terminal_record")
        teams_raw = data["teams"]
        skips_raw = data["skips_remaining"]
        return cls(
            match_id=str(data["match_id"]),
            players=players,
            universe_id=str(data["universe_id"]),
            mode=str(data["mode"]),
            config=DraftConfigSnapshot.from_dict(data["config"]),
            catalog=tuple(CatalogEntry.from_dict(c) for c in data["catalog"]),
            dataset_version=str(data["dataset_version"]),
            starting_player_id=str(data["starting_player_id"]),
            teams={
                str(pid): {str(r): str(cid) for r, cid in dict(teams_raw[pid]).items()}
                for pid in players
            },
            skips_remaining={str(pid): int(skips_raw[pid]) for pid in players},
            held_character=CatalogEntry.from_dict(held) if held is not None else None,
            last_skipped_id=(
                str(data["last_skipped_id"])
                if data.get("last_skipped_id") is not None
                else None
            ),
            status=MatchStatus(data["status"]),
            terminal_record=TerminalRecord.from_dict(term) if term is not None else None,
            revision=int(data["revision"]),
            timestamps=dict(data.get("timestamps") or {}),
        )

    @classmethod
    def from_json(cls, raw: str) -> DraftSnapshot:
        return cls.from_dict(json.loads(raw))


@dataclass(frozen=True, slots=True)
class ActionResult:
    """Result returned by every engine transition."""

    accepted: bool
    error_code: ErrorCode | None
    snapshot: DraftSnapshot
    public_view: PublicDraftView
    events: tuple[DraftEvent, ...] = ()
    completed_output: CompletedDraftOutput | None = None
    terminal_record: TerminalRecord | None = None
