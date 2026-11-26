"""Pure deterministic match resolution engine (Module 3 — RES-1.0)."""

from __future__ import annotations

from typing import Any, Mapping, Protocol

from app.resolution.errors import DatasetUnavailableError, ResolutionErrorCode
from app.resolution.invariants import validate_resolution_invariants
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
)
from app.scoring import (
    BatchValidationError,
    DatasetErrorCode,
    DatasetManifest,
    DatasetRecord,
    DatasetValidationError,
    InMemoryDatasetRepository,
    SCORE_1_0_CONFIG,
    SCORING_ROLES,
    score_record,
)
from app.scoring.models import is_strict_int

_REQUEST_FIELDS = frozenset(
    {
        "match_id",
        "universe_id",
        "game_mode",
        "starting_player",
        "dataset_version",
        "players",
        "teams",
    }
)
_SLOT_SET = frozenset(PLAYER_SLOTS)
_ROLE_SET = frozenset(SCORING_ROLES)


class DatasetReader(Protocol):
    """Read-only dataset boundary injected into Module 3."""

    def load_manifest(self, dataset_version: str) -> DatasetManifest: ...

    def get_character(self, dataset_version: str, character_id: str) -> DatasetRecord: ...


class RepositoryDatasetReader:
    """Adapter bridging Module 2's ``InMemoryDatasetRepository`` to ``DatasetReader``."""

    def __init__(self, repository: InMemoryDatasetRepository) -> None:
        self._repository = repository

    def load_manifest(self, dataset_version: str) -> DatasetManifest:
        return self._repository.load_version(dataset_version)

    def get_character(self, dataset_version: str, character_id: str) -> DatasetRecord:
        return self._repository.get_character_for_resolution(dataset_version, character_id)


def _fail(
    code: ResolutionErrorCode,
    message: str,
    **details: Any,
) -> MatchResolutionFailure:
    return MatchResolutionFailure(error_code=code, message=message, details=details)


def _is_non_empty_str(val: Any) -> bool:
    return isinstance(val, str) and bool(val.strip())


def _extract_request_fields(
    request: ResolveRequest | Mapping[str, Any],
) -> tuple[dict[str, Any] | None, MatchResolutionFailure | None]:
    if isinstance(request, ResolveRequest):
        return {
            "match_id": request.match_id,
            "universe_id": request.universe_id,
            "game_mode": request.game_mode,
            "starting_player": request.starting_player,
            "dataset_version": request.dataset_version,
            "players": request.players,
            "teams": request.teams,
        }, None
    if not isinstance(request, Mapping):
        return None, _fail(
            ResolutionErrorCode.MALFORMED_REQUEST,
            "Request must be a ResolveRequest or mapping",
        )
    keys = set(request.keys())
    if not all(isinstance(k, str) for k in keys):
        return None, _fail(
            ResolutionErrorCode.MALFORMED_REQUEST,
            "Request keys must be strings",
        )
    missing = sorted(_REQUEST_FIELDS - keys)
    unknown = sorted(keys - _REQUEST_FIELDS)
    if missing or unknown:
        return None, _fail(
            ResolutionErrorCode.MALFORMED_REQUEST,
            "Request missing required fields or contains unknown fields",
            missing=missing,
            unknown=unknown,
        )
    return dict(request), None


def _validate_request_stages_1_to_4(
    request: ResolveRequest | Mapping[str, Any],
) -> tuple[dict[str, Any] | None, MatchResolutionFailure | None]:
    """Execute fail-fast validation Stages 1-4 without accessing the dataset."""
    # Stage 1: MALFORMED_REQUEST
    fields, err = _extract_request_fields(request)
    if err is not None or fields is None:
        return None, err

    for name in ("match_id", "universe_id", "dataset_version"):
        if not _is_non_empty_str(fields[name]):
            return None, _fail(
                ResolutionErrorCode.MALFORMED_REQUEST,
                f"{name} must be a non-empty string",
                field=name,
            )

    game_mode = fields["game_mode"]
    if not isinstance(game_mode, str) or game_mode not in VALID_GAME_MODES:
        return None, _fail(
            ResolutionErrorCode.MALFORMED_REQUEST,
            "game_mode must be 'ranked' or 'friendly'",
            field="game_mode",
        )

    starting_player = fields["starting_player"]
    if not isinstance(starting_player, str) or starting_player not in _SLOT_SET:
        return None, _fail(
            ResolutionErrorCode.MALFORMED_REQUEST,
            "starting_player must be 'player_1' or 'player_2'",
            field="starting_player",
        )

    players = fields["players"]
    if not isinstance(players, Mapping) or set(players.keys()) != _SLOT_SET:
        return None, _fail(
            ResolutionErrorCode.MALFORMED_REQUEST,
            "players must contain exactly 'player_1' and 'player_2'",
            field="players",
        )
    for slot in PLAYER_SLOTS:
        if not _is_non_empty_str(players[slot]):
            return None, _fail(
                ResolutionErrorCode.MALFORMED_REQUEST,
                f"players[{slot!r}] must be a non-empty string",
                slot=slot,
            )
    if players["player_1"] == players["player_2"]:
        return None, _fail(
            ResolutionErrorCode.MALFORMED_REQUEST,
            "player_1 and player_2 must be distinct",
            field="players",
        )

    teams = fields["teams"]
    if not isinstance(teams, Mapping) or set(teams.keys()) != _SLOT_SET:
        return None, _fail(
            ResolutionErrorCode.MALFORMED_REQUEST,
            "teams must contain exactly 'player_1' and 'player_2'",
            field="teams",
        )
    for slot in PLAYER_SLOTS:
        team = teams[slot]
        if not isinstance(team, Mapping):
            return None, _fail(
                ResolutionErrorCode.MALFORMED_REQUEST,
                f"teams[{slot!r}] must be a mapping",
                slot=slot,
            )
        for k, v in team.items():
            if not isinstance(k, str):
                return None, _fail(
                    ResolutionErrorCode.MALFORMED_REQUEST,
                    f"teams[{slot!r}] contains a non-string role key",
                    slot=slot,
                )
            if not _is_non_empty_str(v):
                return None, _fail(
                    ResolutionErrorCode.MALFORMED_REQUEST,
                    f"teams[{slot!r}][{k!r}] character_id must be a non-empty string",
                    slot=slot,
                    role=k,
                )

    # Stage 2: INVALID_ROLE (player_1 before player_2, unknown roles lexicographically)
    for slot in PLAYER_SLOTS:
        unknown_roles = sorted(k for k in teams[slot] if k not in _ROLE_SET)
        if unknown_roles:
            bad_role = unknown_roles[0]
            return None, _fail(
                ResolutionErrorCode.INVALID_ROLE,
                f"Invalid role {bad_role!r} in {slot}",
                slot=slot,
                role=bad_role,
            )

    # Stage 3: INCOMPLETE_TEAM (player_1 before player_2, canonical role order)
    for slot in PLAYER_SLOTS:
        team = teams[slot]
        for role in SCORING_ROLES:
            if role not in team:
                return None, _fail(
                    ResolutionErrorCode.INCOMPLETE_TEAM,
                    f"Team {slot} is missing role {role!r}",
                    slot=slot,
                    role=role,
                )

    # Stage 4: DUPLICATE_CHARACTER (player_1 before player_2, canonical role order)
    seen_chars: set[str] = set()
    for slot in PLAYER_SLOTS:
        team = teams[slot]
        for role in SCORING_ROLES:
            cid = team[role]
            if cid in seen_chars:
                return None, _fail(
                    ResolutionErrorCode.DUPLICATE_CHARACTER,
                    f"Duplicate character_id {cid!r} at {slot}.{role}",
                    slot=slot,
                    role=role,
                    character_id=cid,
                )
            seen_chars.add(cid)

    return fields, None


def _verify_and_extract_participant(
    record: Any,
    *,
    expected_character_id: str,
    expected_scoring_version: str,
    role: str,
    slot: str,
) -> tuple[MatchupParticipant | None, MatchResolutionFailure | None]:
    """Stage 9: Verify retrieved record integrity and recompute via Module 2."""
    if not isinstance(record, DatasetRecord):
        return None, _fail(
            ResolutionErrorCode.CHARACTER_RECORD_INVALID,
            f"Invalid record structure for {expected_character_id!r}",
            slot=slot,
            role=role,
            character_id=expected_character_id,
        )
    if record.character_id != expected_character_id:
        return None, _fail(
            ResolutionErrorCode.CHARACTER_RECORD_INVALID,
            f"Record identity mismatch: expected {expected_character_id!r}, got {record.character_id!r}",
            slot=slot,
            role=role,
            character_id=expected_character_id,
        )
    if record.scoring_version != expected_scoring_version:
        return None, _fail(
            ResolutionErrorCode.CHARACTER_RECORD_INVALID,
            f"Record scoring_version mismatch for {expected_character_id!r}",
            slot=slot,
            role=role,
            character_id=expected_character_id,
        )

    # Validate stored scores dict structure & strict integer types
    if not isinstance(record.scores, Mapping) or set(record.scores.keys()) != _ROLE_SET:
        return None, _fail(
            ResolutionErrorCode.CHARACTER_RECORD_INVALID,
            f"Stored scores missing or invalid keys for {expected_character_id!r}",
            slot=slot,
            role=role,
            character_id=expected_character_id,
        )
    for r in SCORING_ROLES:
        if not is_strict_int(record.scores[r]):
            return None, _fail(
                ResolutionErrorCode.CHARACTER_RECORD_INVALID,
                f"Stored score for {expected_character_id!r}.{r} must be an integer",
                slot=slot,
                role=role,
                character_id=expected_character_id,
            )

    # Reverify ratings and all 7 role scores using Module 2's authoritative logic
    try:
        recomputed = score_record(
            {
                "character_id": record.character_id,
                "power": record.power,
                "fit": dict(record.fit),
            },
            config=SCORE_1_0_CONFIG,
        )
    except BatchValidationError as exc:
        return None, _fail(
            ResolutionErrorCode.CHARACTER_RECORD_INVALID,
            f"Module 2 validation failed for {expected_character_id!r}: {exc}",
            slot=slot,
            role=role,
            character_id=expected_character_id,
        )

    if dict(record.scores) != dict(recomputed.scores):
        return None, _fail(
            ResolutionErrorCode.CHARACTER_RECORD_INVALID,
            f"Stored scores inconsistent with Module 2 calculation for {expected_character_id!r}",
            slot=slot,
            role=role,
            character_id=expected_character_id,
        )

    return MatchupParticipant(
        character_id=record.character_id,
        power=recomputed.power,
        fit=recomputed.fit[role],
        score=recomputed.scores[role],
    ), None


def resolve_match(
    request: ResolveRequest | Mapping[str, Any],
    dataset_reader: DatasetReader,
) -> MatchResolutionSuccess | MatchResolutionFailure:
    """Resolve a completed 14-character draft deterministically (RES-1.0)."""
    # Stages 1-4 (no dataset access)
    fields, failure = _validate_request_stages_1_to_4(request)
    if failure is not None or fields is None:
        return failure  # type: ignore[return-value]

    dataset_version: str = fields["dataset_version"]

    # Stages 5, 5b, 6: Load and verify pinned dataset manifest
    try:
        manifest = dataset_reader.load_manifest(dataset_version)
    except DatasetUnavailableError as exc:
        return _fail(
            ResolutionErrorCode.DATASET_UNAVAILABLE,
            f"Dataset {dataset_version!r} is temporarily unavailable: {exc}",
            dataset_version=dataset_version,
        )
    except DatasetValidationError as exc:
        if exc.code is DatasetErrorCode.VERSION_NOT_FOUND:
            return _fail(
                ResolutionErrorCode.DATASET_NOT_FOUND,
                f"Dataset {dataset_version!r} not found",
                dataset_version=dataset_version,
            )
        return _fail(
            ResolutionErrorCode.DATASET_INTEGRITY_FAILURE,
            f"Dataset integrity verification failed: {exc.message}",
            dataset_version=dataset_version,
        )

    if not isinstance(manifest, DatasetManifest) or manifest.dataset_version != dataset_version:
        return _fail(
            ResolutionErrorCode.DATASET_INTEGRITY_FAILURE,
            "Invalid dataset manifest or version mismatch",
            dataset_version=dataset_version,
        )

    try:
        computed_hash = manifest.compute_content_hash()
    except Exception:
        return _fail(
            ResolutionErrorCode.DATASET_INTEGRITY_FAILURE,
            "Dataset manifest canonical hash computation failed",
            dataset_version=dataset_version,
        )
    if manifest.content_hash != computed_hash:
        return _fail(
            ResolutionErrorCode.DATASET_INTEGRITY_FAILURE,
            "Dataset manifest content_hash mismatch",
            dataset_version=dataset_version,
        )

    # Stage 7: UNSUPPORTED_SCORING_VERSION
    if manifest.scoring_version not in SUPPORTED_SCORING_VERSIONS:
        return _fail(
            ResolutionErrorCode.UNSUPPORTED_SCORING_VERSION,
            f"Unsupported scoring version {manifest.scoring_version!r}",
            dataset_version=dataset_version,
            scoring_version=manifest.scoring_version,
        )

    # Stage 8 (CHARACTER_NOT_FOUND) & Stage 9 (CHARACTER_RECORD_INVALID)
    # Check Stage 8 across all 14 slots before Stage 9 so deterministic precedence holds.
    teams = fields["teams"]
    fetched_records: dict[tuple[str, str], DatasetRecord] = {}
    for slot in PLAYER_SLOTS:
        for role in SCORING_ROLES:
            cid = teams[slot][role]
            try:
                rec = dataset_reader.get_character(dataset_version, cid)
            except DatasetUnavailableError as exc:
                return _fail(
                    ResolutionErrorCode.DATASET_UNAVAILABLE,
                    f"Dataset {dataset_version!r} is temporarily unavailable: {exc}",
                    dataset_version=dataset_version,
                )
            except DatasetValidationError as exc:
                if exc.code is DatasetErrorCode.VERSION_NOT_FOUND:
                    return _fail(
                        ResolutionErrorCode.DATASET_NOT_FOUND,
                        f"Dataset {dataset_version!r} not found",
                        dataset_version=dataset_version,
                    )
                return _fail(
                    ResolutionErrorCode.DATASET_INTEGRITY_FAILURE,
                    f"Dataset integrity verification failed: {exc.message}",
                    dataset_version=dataset_version,
                )
            except KeyError:
                return _fail(
                    ResolutionErrorCode.CHARACTER_NOT_FOUND,
                    f"Character {cid!r} not found in dataset {dataset_version!r}",
                    slot=slot,
                    role=role,
                    character_id=cid,
                    dataset_version=dataset_version,
                )
            fetched_records[(slot, role)] = rec

    participants: dict[tuple[str, str], MatchupParticipant] = {}
    for slot in PLAYER_SLOTS:
        for role in SCORING_ROLES:
            cid = teams[slot][role]
            participant, rec_err = _verify_and_extract_participant(
                fetched_records[(slot, role)],
                expected_character_id=cid,
                expected_scoring_version=manifest.scoring_version,
                role=role,
                slot=slot,
            )
            if rec_err is not None or participant is None:
                return rec_err  # type: ignore[return-value]
            participants[(slot, role)] = participant

    # Resolve 7 same-role matchups in canonical role order
    matchups: list[RoleMatchup] = []
    wins_p1 = 0
    wins_p2 = 0
    draws = 0
    total_p1 = 0
    total_p2 = 0

    for role in SCORING_ROLES:
        p1_part = participants[("player_1", role)]
        p2_part = participants[("player_2", role)]
        total_p1 += p1_part.score
        total_p2 += p2_part.score
        margin = p1_part.score - p2_part.score
        if margin > 0:
            winner = MatchupWinner.PLAYER_1
            wins_p1 += 1
        elif margin < 0:
            winner = MatchupWinner.PLAYER_2
            wins_p2 += 1
        else:
            winner = MatchupWinner.DRAW
            draws += 1
        matchups.append(
            RoleMatchup(
                role=role,
                player_1=p1_part,
                player_2=p2_part,
                winner=winner,
                margin=margin,
            )
        )

    if wins_p1 > wins_p2:
        outcome = MatchOutcome.PLAYER_1_WIN
        decided_by = DecidedBy.MATCHUP_COUNT
    elif wins_p2 > wins_p1:
        outcome = MatchOutcome.PLAYER_2_WIN
        decided_by = DecidedBy.MATCHUP_COUNT
    elif total_p1 > total_p2:
        outcome = MatchOutcome.PLAYER_1_WIN
        decided_by = DecidedBy.COMBINED_SCORE
    elif total_p2 > total_p1:
        outcome = MatchOutcome.PLAYER_2_WIN
        decided_by = DecidedBy.COMBINED_SCORE
    else:
        outcome = MatchOutcome.DRAW
        decided_by = DecidedBy.NONE

    result = MatchResolutionSuccess(
        resolution_version=RESOLUTION_VERSION,
        scoring_version=manifest.scoring_version,
        dataset_version=dataset_version,
        match_id=fields["match_id"],
        universe_id=fields["universe_id"],
        game_mode=fields["game_mode"],
        starting_player=fields["starting_player"],
        players={slot: fields["players"][slot] for slot in PLAYER_SLOTS},
        outcome=outcome,
        decided_by=decided_by,
        summary=ResolutionSummary(
            wins_player_1=wins_p1,
            wins_player_2=wins_p2,
            draws=draws,
            total_player_1=total_p1,
            total_player_2=total_p2,
            total_margin=total_p1 - total_p2,
        ),
        matchups=tuple(matchups),
    )
    validate_resolution_invariants(result)
    return result
