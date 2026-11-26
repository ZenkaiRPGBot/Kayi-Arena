"""Module 1 CompletedDraftOutput -> Module 3 ResolveRequest integration adapter."""

from __future__ import annotations

from typing import Sequence

from app.engine.models import CompletedDraftOutput, ROLES as ENGINE_ROLES
from app.resolution.engine import DatasetReader, resolve_match
from app.resolution.models import (
    MatchResolutionFailure,
    MatchResolutionSuccess,
    ResolveRequest,
)
from app.scoring import SCORING_ROLES

ENGINE_TO_SCORING_ROLE: dict[str, str] = dict(zip(ENGINE_ROLES, SCORING_ROLES))


def build_resolve_request_from_completed_draft(
    completed: CompletedDraftOutput,
    *,
    player_order: Sequence[str] | None = None,
) -> ResolveRequest:
    """Convert Module 1's ``CompletedDraftOutput`` into a ``ResolveRequest``.

    Preserves original player identities and team mappings without reordering by
    player ID or starting order.
    """
    team_keys = list(completed.teams.keys())
    if player_order is not None:
        ordered = list(player_order)
    else:
        ordered = team_keys

    if len(ordered) != 2:
        raise ValueError("CompletedDraftOutput must have exactly 2 players")
    p1_id, p2_id = ordered[0], ordered[1]
    if p1_id not in completed.teams or p2_id not in completed.teams:
        raise ValueError("player_order IDs must match completed.teams keys")

    if completed.starting_player_id == p1_id:
        starting_slot = "player_1"
    elif completed.starting_player_id == p2_id:
        starting_slot = "player_2"
    else:
        raise ValueError("starting_player_id does not belong to completed.teams")

    def _convert_team(raw_team: dict[str, str]) -> dict[str, str]:
        converted: dict[str, str] = {}
        for role, cid in raw_team.items():
            mapped = ENGINE_TO_SCORING_ROLE.get(role, role)
            converted[mapped] = cid
        return converted

    return ResolveRequest(
        match_id=completed.match_id,
        universe_id=completed.universe_id,
        game_mode=completed.mode,
        starting_player=starting_slot,
        dataset_version=completed.dataset_version,
        players={"player_1": p1_id, "player_2": p2_id},
        teams={
            "player_1": _convert_team(completed.teams[p1_id]),
            "player_2": _convert_team(completed.teams[p2_id]),
        },
    )


def resolve_completed_draft(
    completed: CompletedDraftOutput,
    dataset_reader: DatasetReader,
    *,
    player_order: Sequence[str] | None = None,
) -> MatchResolutionSuccess | MatchResolutionFailure:
    """Resolve a Module 1 ``CompletedDraftOutput`` directly via Module 3."""
    request = build_resolve_request_from_completed_draft(
        completed, player_order=player_order
    )
    return resolve_match(request, dataset_reader)
