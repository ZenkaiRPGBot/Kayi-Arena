"""Invariant verification for Core Drafting Engine snapshots (Section 10.1)."""

from __future__ import annotations

from app.engine.errors import EngineConfigError
from app.engine.models import DraftPhase, DraftSnapshot, MatchStatus, MIN_POOL_SIZE


class InvariantViolationError(EngineConfigError):
    """Raised when a snapshot violates a Core Drafting Engine invariant."""


def validate_snapshot_invariants(snapshot: DraftSnapshot) -> None:
    """Verify all structural and state-machine invariants on ``snapshot``."""
    p1, p2 = snapshot.players
    if not p1 or not p2 or p1 == p2:
        raise InvariantViolationError("Players must be two distinct non-empty IDs")
    if not snapshot.match_id:
        raise InvariantViolationError("match_id must be non-empty")
    if not snapshot.dataset_version:
        raise InvariantViolationError("dataset_version must be non-empty")
    if snapshot.starting_player_id not in snapshot.players:
        raise InvariantViolationError("starting_player_id must belong to players")

    if len(snapshot.catalog) < MIN_POOL_SIZE:
        raise InvariantViolationError(f"Catalog must contain at least {MIN_POOL_SIZE} characters")

    catalog_ids = [entry.character_id for entry in snapshot.catalog]
    catalog_id_set = set(catalog_ids)
    if len(catalog_id_set) != len(catalog_ids):
        raise InvariantViolationError("Catalog contains duplicate character IDs")

    weights = snapshot.config.rarity_weights
    if not weights or any(float(w) <= 0.0 for w in weights.values()):
        raise InvariantViolationError("All configured rarity weights must be positive")
    for entry in snapshot.catalog:
        if entry.rarity_id not in weights:
            raise InvariantViolationError(
                f"Character {entry.character_id!r} has unknown rarity {entry.rarity_id!r}"
            )

    if snapshot.revision < 0:
        raise InvariantViolationError("Revision must be non-negative")

    valid_roles = set(snapshot.config.roles)
    if len(valid_roles) != 7:
        raise InvariantViolationError("Configuration must define exactly 7 unique roles")

    # Invariant 2 & 1: valid roles, unique character assignments, disjoint sets
    seen_assigned: set[str] = set()
    counts: dict[str, int] = {}
    for pid in snapshot.players:
        if pid not in snapshot.teams or pid not in snapshot.skips_remaining:
            raise InvariantViolationError(f"Missing team or skips entry for {pid!r}")
        team = snapshot.teams[pid]
        counts[pid] = len(team)
        for role, cid in team.items():
            if role not in valid_roles:
                raise InvariantViolationError(f"Invalid role {role!r} in team {pid!r}")
            if cid not in catalog_id_set:
                raise InvariantViolationError(f"Assigned character {cid!r} not in catalog")
            if cid in seen_assigned:
                raise InvariantViolationError(f"Duplicate character assignment {cid!r}")
            seen_assigned.add(cid)

    # Invariant 3: assignment counts differ by at most 1, starter never behind
    other = p2 if snapshot.starting_player_id == p1 else p1
    diff = counts[snapshot.starting_player_id] - counts[other]
    if diff not in (0, 1):
        raise InvariantViolationError(
            f"Invalid turn balance: starter={counts[snapshot.starting_player_id]}, other={counts[other]}"
        )

    # Invariant 4: skips remaining within [0, skips_per_player]
    max_skips = snapshot.config.skips_per_player
    for pid, skips in snapshot.skips_remaining.items():
        if not (0 <= skips <= max_skips):
            raise InvariantViolationError(f"Skips out of range for {pid!r}: {skips}")

    # Invariant 5: held_character & last_skipped rules per status/phase
    if snapshot.held_character is not None:
        held_id = snapshot.held_character.character_id
        if held_id not in catalog_id_set or held_id in seen_assigned:
            raise InvariantViolationError("Held character must be in catalog and unassigned")

    available_ids = {c.character_id for c in snapshot.available_pool()}

    if snapshot.status is MatchStatus.ACTIVE:
        if snapshot.terminal_record is not None:
            raise InvariantViolationError("Active match must not have a terminal_record")
        if snapshot.total_assignments >= 14:
            raise InvariantViolationError("Active match cannot already have 14 assignments")
        if snapshot.held_character is not None and snapshot.phase is not DraftPhase.AWAITING_DECISION:
            raise InvariantViolationError("Held character requires AWAITING_DECISION")
        if snapshot.held_character is None and snapshot.phase is not DraftPhase.AWAITING_SHUFFLE:
            raise InvariantViolationError("No held character requires AWAITING_SHUFFLE")
        # Invariant 8: last_skipped_id set only while AWAITING_SHUFFLE and must be in available pool
        if snapshot.last_skipped_id is not None:
            if snapshot.phase is not DraftPhase.AWAITING_SHUFFLE:
                raise InvariantViolationError("last_skipped_id may only be set in AWAITING_SHUFFLE")
            if snapshot.last_skipped_id not in available_ids:
                raise InvariantViolationError("last_skipped_id must be in the available pool")
        # Invariant 11: eligible set non-empty when AWAITING_SHUFFLE
        if snapshot.phase is DraftPhase.AWAITING_SHUFFLE and not snapshot.eligible_pool():
            raise InvariantViolationError("Eligible pool must be non-empty in AWAITING_SHUFFLE")
    else:
        # Terminal states (COMPLETED or TERMINATED)
        if snapshot.held_character is not None:
            raise InvariantViolationError("Terminal state must not hold a character")
        if snapshot.last_skipped_id is not None:
            raise InvariantViolationError("Terminal state must have empty last_skipped_id")
        if snapshot.status is MatchStatus.COMPLETED:
            if snapshot.total_assignments != 14:
                raise InvariantViolationError("COMPLETED state requires 14 assignments")
            if snapshot.terminal_record is not None:
                raise InvariantViolationError("COMPLETED state must not have terminal_record")
        elif snapshot.status is MatchStatus.TERMINATED:
            if snapshot.terminal_record is None:
                raise InvariantViolationError("TERMINATED state requires a terminal_record")

    # Invariant 1: pool + held + team A + team B == catalog
    held_set = {snapshot.held_character.character_id} if snapshot.held_character else set()
    if available_ids | held_set | seen_assigned != catalog_id_set:
        raise InvariantViolationError("Partition of catalog characters does not match catalog")
