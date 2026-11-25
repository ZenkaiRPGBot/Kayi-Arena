"""Pure state-machine transitions for Kayi Arena Module 1 (Core Drafting Engine)."""

from __future__ import annotations

import math
from typing import Any, Mapping, Sequence

from app.engine.errors import EngineConfigError, ErrorCode
from app.engine.invariants import validate_snapshot_invariants
from app.engine.models import (
    ActionResult,
    CatalogEntry,
    CompletedDraftOutput,
    DEFAULT_SKIPS_PER_PLAYER,
    DraftConfigSnapshot,
    DraftEvent,
    DraftPhase,
    DraftSnapshot,
    MIN_POOL_SIZE,
    MatchStatus,
    PublicDraftView,
    PublicTerminalSummary,
    ROLES,
    TOTAL_ASSIGNMENTS,
    TerminalRecord,
    TerminationReason,
)
from app.engine.randomness import (
    DrawSource,
    SystemDrawSource,
    compute_character_probabilities,
)


def project_public_view(snapshot: DraftSnapshot) -> PublicDraftView:
    """Pure projection from internal snapshot to player-facing view (Section 5.5)."""
    terminal_summary = (
        PublicTerminalSummary(
            reason=snapshot.terminal_record.reason,
            subject_player_id=snapshot.terminal_record.subject_player_id,
        )
        if snapshot.terminal_record is not None
        else None
    )
    return PublicDraftView(
        match_id=snapshot.match_id,
        players=snapshot.players,
        universe_id=snapshot.universe_id,
        mode=snapshot.mode,
        status=snapshot.status,
        phase=snapshot.phase,
        revision=snapshot.revision,
        active_player_id=snapshot.active_player_id,
        progress=snapshot.total_assignments,
        turn_number=snapshot.turn_number,
        teams={pid: dict(snapshot.teams[pid]) for pid in snapshot.players},
        remaining_roles=snapshot.remaining_roles(),
        skips_remaining=dict(snapshot.skips_remaining),
        held_character=snapshot.held_character,
        can_skip=snapshot.can_skip(),
        terminal_summary=terminal_summary,
    )


def character_probabilities(snapshot: DraftSnapshot) -> dict[str, float]:
    """Return exact draw probability for each eligible character in ``snapshot``."""
    if snapshot.status is not MatchStatus.ACTIVE:
        return {}
    return compute_character_probabilities(
        snapshot.eligible_pool(),
        snapshot.config.rarity_weights,
    )


def _reject(snapshot: DraftSnapshot, code: ErrorCode) -> ActionResult:
    return ActionResult(
        accepted=False,
        error_code=code,
        snapshot=snapshot,
        public_view=project_public_view(snapshot),
        events=(),
    )


def _merge_timestamps(
    existing: Mapping[str, Any],
    timestamp: Mapping[str, Any] | None,
) -> dict[str, Any]:
    merged = dict(existing)
    if timestamp:
        merged.update(timestamp)
    return merged


def start_draft(
    *,
    match_id: str,
    players: tuple[str, str],
    universe_id: str,
    mode: str,
    catalog: Sequence[CatalogEntry],
    rarity_weights: Mapping[str, float],
    dataset_version: str,
    skips_per_player: int = DEFAULT_SKIPS_PER_PLAYER,
    roles: Sequence[str] = ROLES,
    draw_source: DrawSource | None = None,
    forced_starter: str | None = None,
    timestamp: Mapping[str, Any] | None = None,
) -> ActionResult:
    """Initialize a new draft at revision 0 in AWAITING_SHUFFLE."""
    if not match_id or not isinstance(match_id, str):
        raise EngineConfigError("match_id must be a non-empty string")
    if len(players) != 2:
        raise EngineConfigError("Exactly 2 players are required")
    p1, p2 = players
    if not p1 or not p2 or p1 == p2:
        raise EngineConfigError("Players must be two distinct non-empty identifiers")
    if not universe_id:
        raise EngineConfigError("universe_id must be non-empty")
    if not mode:
        raise EngineConfigError("mode must be non-empty")
    if not dataset_version:
        raise EngineConfigError("dataset_version must be non-empty")
    if skips_per_player != DEFAULT_SKIPS_PER_PLAYER:
        raise EngineConfigError(f"skips_per_player must be {DEFAULT_SKIPS_PER_PLAYER}")

    roles_tuple = tuple(roles)
    if roles_tuple != ROLES:
        raise EngineConfigError("roles must match the 7 predefined Kayi Arena roles")

    if not rarity_weights:
        raise EngineConfigError("rarity_weights must not be empty")
    clean_weights: dict[str, float] = {}
    for rarity_id, raw_weight in rarity_weights.items():
        weight = float(raw_weight)
        if not rarity_id or not math.isfinite(weight) or weight <= 0.0:
            raise EngineConfigError(
                f"Rarity {rarity_id!r} must have a finite positive weight"
            )
        clean_weights[str(rarity_id)] = weight

    catalog_tuple = tuple(catalog)
    if len(catalog_tuple) < MIN_POOL_SIZE:
        raise EngineConfigError(
            f"Character pool must contain at least {MIN_POOL_SIZE} unique characters"
        )
    seen_ids: set[str] = set()
    for entry in catalog_tuple:
        if not entry.character_id:
            raise EngineConfigError("Character ID must be non-empty")
        if entry.character_id in seen_ids:
            raise EngineConfigError(f"Duplicate character ID: {entry.character_id!r}")
        if entry.rarity_id not in clean_weights:
            raise EngineConfigError(
                f"Character {entry.character_id!r} references unknown/unweighted rarity {entry.rarity_id!r}"
            )
        seen_ids.add(entry.character_id)

    source = draw_source or SystemDrawSource()
    if forced_starter is not None:
        if forced_starter not in players:
            raise EngineConfigError("forced_starter must belong to players")
        starter = forced_starter
    else:
        starter = source.choose_starting_player((p1, p2))
        if starter not in players:
            raise EngineConfigError("DrawSource returned an unknown starting player")

    snapshot = DraftSnapshot(
        match_id=match_id,
        players=(p1, p2),
        universe_id=universe_id,
        mode=mode,
        config=DraftConfigSnapshot(
            rarity_weights=clean_weights,
            skips_per_player=skips_per_player,
            roles=roles_tuple,
        ),
        catalog=catalog_tuple,
        dataset_version=dataset_version,
        starting_player_id=starter,
        teams={p1: {}, p2: {}},
        skips_remaining={p1: skips_per_player, p2: skips_per_player},
        held_character=None,
        last_skipped_id=None,
        status=MatchStatus.ACTIVE,
        terminal_record=None,
        revision=0,
        timestamps=dict(timestamp or {}),
    )
    validate_snapshot_invariants(snapshot)
    return ActionResult(
        accepted=True,
        error_code=None,
        snapshot=snapshot,
        public_view=project_public_view(snapshot),
        events=(DraftEvent(action="start", actor_id=starter, revision=0),),
    )


def _validate_draft_actor(
    snapshot: DraftSnapshot,
    *,
    player_id: str,
    expected_revision: int,
) -> ErrorCode | None:
    """Validation order: active -> known player -> revision -> active turn."""
    if snapshot.status is not MatchStatus.ACTIVE:
        return ErrorCode.MATCH_NOT_ACTIVE
    if player_id not in snapshot.players:
        return ErrorCode.UNKNOWN_PLAYER
    if expected_revision != snapshot.revision:
        return ErrorCode.STALE_REVISION
    if player_id != snapshot.active_player_id:
        return ErrorCode.NOT_YOUR_TURN
    return None


def shuffle(
    snapshot: DraftSnapshot,
    *,
    player_id: str,
    expected_revision: int,
    draw_source: DrawSource | None = None,
    timestamp: Mapping[str, Any] | None = None,
) -> ActionResult:
    """Draw one character from the eligible pool and hold it."""
    err = _validate_draft_actor(
        snapshot, player_id=player_id, expected_revision=expected_revision
    )
    if err is not None:
        return _reject(snapshot, err)
    if snapshot.phase is not DraftPhase.AWAITING_SHUFFLE:
        return _reject(snapshot, ErrorCode.WRONG_PHASE)

    eligible = snapshot.eligible_pool()
    if not eligible:
        raise EngineConfigError("Eligible character pool unexpectedly empty")

    source = draw_source or SystemDrawSource()
    drawn = source.draw_character(eligible, snapshot.config.rarity_weights)
    if not (any(c is drawn for c in eligible) or drawn in eligible):
        raise EngineConfigError("DrawSource returned a character outside the eligible set")

    next_rev = snapshot.revision + 1
    next_snapshot = DraftSnapshot(
        match_id=snapshot.match_id,
        players=snapshot.players,
        universe_id=snapshot.universe_id,
        mode=snapshot.mode,
        config=snapshot.config,
        catalog=snapshot.catalog,
        dataset_version=snapshot.dataset_version,
        starting_player_id=snapshot.starting_player_id,
        teams={pid: dict(team) for pid, team in snapshot.teams.items()},
        skips_remaining=dict(snapshot.skips_remaining),
        held_character=drawn,
        last_skipped_id=None,
        status=MatchStatus.ACTIVE,
        terminal_record=None,
        revision=next_rev,
        timestamps=_merge_timestamps(snapshot.timestamps, timestamp),
    )
    return ActionResult(
        accepted=True,
        error_code=None,
        snapshot=next_snapshot,
        public_view=project_public_view(next_snapshot),
        events=(
            DraftEvent(
                action="shuffle",
                actor_id=player_id,
                revision=next_rev,
                character=drawn,
            ),
        ),
    )


def assign_role(
    snapshot: DraftSnapshot,
    *,
    player_id: str,
    role: str,
    expected_revision: int,
    timestamp: Mapping[str, Any] | None = None,
) -> ActionResult:
    """Assign the held character permanently to ``role`` and pass turn or complete."""
    err = _validate_draft_actor(
        snapshot, player_id=player_id, expected_revision=expected_revision
    )
    if err is not None:
        return _reject(snapshot, err)
    if snapshot.phase is not DraftPhase.AWAITING_DECISION or snapshot.held_character is None:
        return _reject(snapshot, ErrorCode.NO_CHARACTER_DRAWN)
    if role not in snapshot.config.roles:
        return _reject(snapshot, ErrorCode.INVALID_ROLE)
    if role in snapshot.teams[player_id]:
        return _reject(snapshot, ErrorCode.ROLE_OCCUPIED)

    held = snapshot.held_character
    new_teams = {pid: dict(team) for pid, team in snapshot.teams.items()}
    new_teams[player_id][role] = held.character_id
    new_total = sum(len(t) for t in new_teams.values())
    next_status = (
        MatchStatus.COMPLETED if new_total == TOTAL_ASSIGNMENTS else MatchStatus.ACTIVE
    )
    next_rev = snapshot.revision + 1

    next_snapshot = DraftSnapshot(
        match_id=snapshot.match_id,
        players=snapshot.players,
        universe_id=snapshot.universe_id,
        mode=snapshot.mode,
        config=snapshot.config,
        catalog=snapshot.catalog,
        dataset_version=snapshot.dataset_version,
        starting_player_id=snapshot.starting_player_id,
        teams=new_teams,
        skips_remaining=dict(snapshot.skips_remaining),
        held_character=None,
        last_skipped_id=None,
        status=next_status,
        terminal_record=None,
        revision=next_rev,
        timestamps=_merge_timestamps(snapshot.timestamps, timestamp),
    )
    completed_output = (
        CompletedDraftOutput(
            match_id=next_snapshot.match_id,
            universe_id=next_snapshot.universe_id,
            mode=next_snapshot.mode,
            starting_player_id=next_snapshot.starting_player_id,
            dataset_version=next_snapshot.dataset_version,
            teams={pid: dict(team) for pid, team in next_snapshot.teams.items()},
        )
        if next_status is MatchStatus.COMPLETED
        else None
    )
    return ActionResult(
        accepted=True,
        error_code=None,
        snapshot=next_snapshot,
        public_view=project_public_view(next_snapshot),
        events=(
            DraftEvent(
                action="assign",
                actor_id=player_id,
                revision=next_rev,
                character=held,
                role=role,
            ),
        ),
        completed_output=completed_output,
    )


def skip_character(
    snapshot: DraftSnapshot,
    *,
    player_id: str,
    expected_revision: int,
    timestamp: Mapping[str, Any] | None = None,
) -> ActionResult:
    """Return held character to pool, decrement skips, and exclude it on next draw."""
    err = _validate_draft_actor(
        snapshot, player_id=player_id, expected_revision=expected_revision
    )
    if err is not None:
        return _reject(snapshot, err)
    if snapshot.phase is not DraftPhase.AWAITING_DECISION or snapshot.held_character is None:
        return _reject(snapshot, ErrorCode.NO_CHARACTER_DRAWN)
    if snapshot.skips_remaining[player_id] <= 0:
        return _reject(snapshot, ErrorCode.NO_SKIPS_REMAINING)
    if (len(snapshot.catalog) - snapshot.total_assignments - 1) <= 0:
        return _reject(snapshot, ErrorCode.SKIP_NOT_POSSIBLE)

    held = snapshot.held_character
    new_skips = dict(snapshot.skips_remaining)
    new_skips[player_id] -= 1
    next_rev = snapshot.revision + 1

    next_snapshot = DraftSnapshot(
        match_id=snapshot.match_id,
        players=snapshot.players,
        universe_id=snapshot.universe_id,
        mode=snapshot.mode,
        config=snapshot.config,
        catalog=snapshot.catalog,
        dataset_version=snapshot.dataset_version,
        starting_player_id=snapshot.starting_player_id,
        teams={pid: dict(team) for pid, team in snapshot.teams.items()},
        skips_remaining=new_skips,
        held_character=None,
        last_skipped_id=held.character_id,
        status=MatchStatus.ACTIVE,
        terminal_record=None,
        revision=next_rev,
        timestamps=_merge_timestamps(snapshot.timestamps, timestamp),
    )
    return ActionResult(
        accepted=True,
        error_code=None,
        snapshot=next_snapshot,
        public_view=project_public_view(next_snapshot),
        events=(
            DraftEvent(
                action="skip",
                actor_id=player_id,
                revision=next_rev,
                character=held,
            ),
        ),
    )


def terminate_draft(
    snapshot: DraftSnapshot,
    *,
    reason: TerminationReason | str,
    subject_player_id: str | None = None,
    source_label: str = "",
    caller_reference: str = "",
    timestamp: Mapping[str, Any] | None = None,
) -> ActionResult:
    """Terminate an active match externally (no revision check, releases held char)."""
    if snapshot.status is not MatchStatus.ACTIVE:
        return _reject(snapshot, ErrorCode.MATCH_NOT_ACTIVE)

    try:
        parsed_reason = (
            reason
            if isinstance(reason, TerminationReason)
            else TerminationReason(str(reason))
        )
    except ValueError:
        return _reject(snapshot, ErrorCode.INVALID_REASON)

    if subject_player_id is not None and subject_player_id not in snapshot.players:
        return _reject(snapshot, ErrorCode.UNKNOWN_PLAYER)

    held = snapshot.held_character
    record = TerminalRecord(
        reason=parsed_reason,
        subject_player_id=subject_player_id,
        source_label=source_label,
        caller_reference=caller_reference,
        held_character_at_termination=held,
    )
    next_rev = snapshot.revision + 1
    next_snapshot = DraftSnapshot(
        match_id=snapshot.match_id,
        players=snapshot.players,
        universe_id=snapshot.universe_id,
        mode=snapshot.mode,
        config=snapshot.config,
        catalog=snapshot.catalog,
        dataset_version=snapshot.dataset_version,
        starting_player_id=snapshot.starting_player_id,
        teams={pid: dict(team) for pid, team in snapshot.teams.items()},
        skips_remaining=dict(snapshot.skips_remaining),
        held_character=None,
        last_skipped_id=None,
        status=MatchStatus.TERMINATED,
        terminal_record=record,
        revision=next_rev,
        timestamps=_merge_timestamps(snapshot.timestamps, timestamp),
    )
    return ActionResult(
        accepted=True,
        error_code=None,
        snapshot=next_snapshot,
        public_view=project_public_view(next_snapshot),
        events=(
            DraftEvent(
                action="terminate",
                actor_id=subject_player_id,
                revision=next_rev,
                character=held,
                reason=parsed_reason,
            ),
        ),
        terminal_record=record,
    )


def restore_snapshot(data: Mapping[str, Any] | str) -> DraftSnapshot:
    """Deserialize and validate an internal snapshot from dict or JSON."""
    try:
        snapshot = (
            DraftSnapshot.from_json(data)
            if isinstance(data, str)
            else DraftSnapshot.from_dict(data)
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise EngineConfigError(f"Invalid draft snapshot payload: {exc}") from exc
    validate_snapshot_invariants(snapshot)
    return snapshot
