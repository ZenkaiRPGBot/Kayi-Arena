"""Tests for normal drafting flow, turn alternation, roles, and skip behavior."""

from __future__ import annotations

import pytest

from app.engine import (
    CatalogEntry,
    DraftPhase,
    ErrorCode,
    MAX_ACCEPTED_DRAFT_ACTIONS,
    MatchStatus,
    ROLES,
    ScriptedDrawSource,
    SeededDrawSource,
    assign_role,
    shuffle,
    skip_character,
    start_draft,
    validate_snapshot_invariants,
)
from tests.conftest import DEFAULT_WEIGHTS, make_catalog


def test_complete_draft_without_skips_fictional_20_pool() -> None:
    """Acceptance criterion 6 & normal draft without skips."""
    catalog = make_catalog(20)
    draws = [c.character_id for c in catalog[:14]]
    source = ScriptedDrawSource(starting_player="p1", draws=draws)

    res = start_draft(
        match_id="m-no-skip",
        players=("p1", "p2"),
        universe_id="u1",
        mode="ranked",
        catalog=catalog,
        rarity_weights=DEFAULT_WEIGHTS,
        dataset_version="ds-v1",
        draw_source=source,
    )
    assert res.accepted
    snap = res.snapshot
    actions = 0

    for turn in range(14):
        expected_actor = "p1" if turn % 2 == 0 else "p2"
        assert snap.active_player_id == expected_actor
        assert snap.phase is DraftPhase.AWAITING_SHUFFLE

        shuf = shuffle(
            snap,
            player_id=expected_actor,
            expected_revision=snap.revision,
            draw_source=source,
        )
        assert shuf.accepted
        actions += 1
        snap = shuf.snapshot
        validate_snapshot_invariants(snap)
        assert snap.phase is DraftPhase.AWAITING_DECISION

        role = ROLES[turn // 2]
        asgn = assign_role(
            snap,
            player_id=expected_actor,
            role=role,
            expected_revision=snap.revision,
        )
        assert asgn.accepted
        actions += 1
        snap = asgn.snapshot
        validate_snapshot_invariants(snap)

    assert snap.status is MatchStatus.COMPLETED
    assert actions == 28 <= MAX_ACCEPTED_DRAFT_ACTIONS
    assert asgn.completed_output is not None
    assert asgn.completed_output.dataset_version == "ds-v1"
    assert asgn.completed_output.starting_player_id == "p1"
    assert len(asgn.completed_output.teams["p1"]) == 7
    assert len(asgn.completed_output.teams["p2"]) == 7
    assert source.starter_calls == 1
    assert source.draw_calls == 14


@pytest.mark.parametrize("starter", ["p1", "p2"])
def test_forced_starter_alternates_turns_and_ends_on_other_player(starter: str) -> None:
    catalog = make_catalog(16)
    source = SeededDrawSource(seed=101)
    res = start_draft(
        match_id=f"m-starter-{starter}",
        players=("p1", "p2"),
        universe_id="u1",
        mode="friendly",
        catalog=catalog,
        rarity_weights=DEFAULT_WEIGHTS,
        dataset_version="ds-1",
        draw_source=source,
        forced_starter=starter,
    )
    assert source.starter_calls == 0  # forced_starter bypasses starter draw call
    snap = res.snapshot
    other = "p2" if starter == "p1" else "p1"
    last_actor = None

    for turn in range(14):
        expected_actor = starter if turn % 2 == 0 else other
        assert snap.active_player_id == expected_actor
        snap = shuffle(
            snap,
            player_id=expected_actor,
            expected_revision=snap.revision,
            draw_source=source,
        ).snapshot
        role = snap.remaining_roles()[expected_actor][0]
        snap = assign_role(
            snap,
            player_id=expected_actor,
            role=role,
            expected_revision=snap.revision,
        ).snapshot
        last_actor = expected_actor

    assert snap.status is MatchStatus.COMPLETED
    assert last_actor == other


def test_skip_keeps_turn_decrements_skips_and_blocks_immediate_redraw() -> None:
    catalog = make_catalog(16)
    # 1st draw: char_000 (skipped) -> 2nd draw: char_001 (skipped) -> 3rd draw: char_000 (assigned) -> 4th: char_001 (opponent draws!)
    draws = ["char_000", "char_001", "char_000", "char_001"] + [f"char_{i:03d}" for i in range(2, 15)]
    source = ScriptedDrawSource(starting_player="p1", draws=draws)

    snap = start_draft(
        match_id="m-skips",
        players=("p1", "p2"),
        universe_id="u1",
        mode="ranked",
        catalog=catalog,
        rarity_weights=DEFAULT_WEIGHTS,
        dataset_version="ds-1",
        draw_source=source,
    ).snapshot

    # Draw 1 -> char_000
    snap = shuffle(snap, player_id="p1", expected_revision=snap.revision, draw_source=source).snapshot
    assert snap.held_character.character_id == "char_000"

    # Skip 1 -> keeps p1's turn, skips=1, char_000 excluded from next draw
    skip1 = skip_character(snap, player_id="p1", expected_revision=snap.revision)
    assert skip1.accepted
    snap = skip1.snapshot
    assert snap.active_player_id == "p1"
    assert snap.skips_remaining["p1"] == 1
    assert snap.last_skipped_id == "char_000"
    assert all(c.character_id != "char_000" for c in snap.eligible_pool())
    assert any(c.character_id == "char_000" for c in snap.available_pool())

    # Draw 2 -> char_001 (cannot be char_000)
    snap = shuffle(snap, player_id="p1", expected_revision=snap.revision, draw_source=source).snapshot
    assert snap.held_character.character_id == "char_001"

    # Consecutive Skip 2 -> skips=0, char_001 excluded, char_000 eligible again!
    skip2 = skip_character(snap, player_id="p1", expected_revision=snap.revision)
    assert skip2.accepted
    snap = skip2.snapshot
    assert snap.active_player_id == "p1"
    assert snap.skips_remaining["p1"] == 0
    assert snap.last_skipped_id == "char_001"
    assert any(c.character_id == "char_000" for c in snap.eligible_pool())
    assert all(c.character_id != "char_001" for c in snap.eligible_pool())

    # Draw 3 -> char_000 returns!
    snap = shuffle(snap, player_id="p1", expected_revision=snap.revision, draw_source=source).snapshot
    assert snap.held_character.character_id == "char_000"

    # Third skip fails with NO_SKIPS_REMAINING
    bad_skip = skip_character(snap, player_id="p1", expected_revision=snap.revision)
    assert not bad_skip.accepted
    assert bad_skip.error_code is ErrorCode.NO_SKIPS_REMAINING

    # Assign char_000, then p2 draws char_001 (opponent can draw previously skipped char)
    snap = assign_role(snap, player_id="p1", role="Captain", expected_revision=snap.revision).snapshot
    assert snap.active_player_id == "p2"
    snap = shuffle(snap, player_id="p2", expected_revision=snap.revision, draw_source=source).snapshot
    assert snap.held_character.character_id == "char_001"


def test_skip_guard_when_no_alternative_exists_in_14_pool() -> None:
    catalog = make_catalog(14)
    source = SeededDrawSource(seed=7)
    snap = start_draft(
        match_id="m-14-guard",
        players=("p1", "p2"),
        universe_id="u1",
        mode="ranked",
        catalog=catalog,
        rarity_weights=DEFAULT_WEIGHTS,
        dataset_version="ds-1",
        draw_source=source,
        forced_starter="p1",
    ).snapshot

    # Complete first 13 turns without skipping
    for turn in range(13):
        actor = snap.active_player_id
        snap = shuffle(snap, player_id=actor, expected_revision=snap.revision, draw_source=source).snapshot
        role = snap.remaining_roles()[actor][0]
        snap = assign_role(snap, player_id=actor, role=role, expected_revision=snap.revision).snapshot

    # Turn 14: p2 draws the last remaining character; pool is now empty
    shuf = shuffle(snap, player_id="p2", expected_revision=snap.revision, draw_source=source)
    snap = shuf.snapshot
    assert len(snap.available_pool()) == 0
    assert shuf.public_view.can_skip is False

    rejected = skip_character(snap, player_id="p2", expected_revision=snap.revision)
    assert not rejected.accepted
    assert rejected.error_code is ErrorCode.SKIP_NOT_POSSIBLE
    assert rejected.snapshot.to_json() == snap.to_json()


def test_complete_draft_with_all_4_skips_uses_max_36_actions() -> None:
    catalog = make_catalog(20)
    source = SeededDrawSource(seed=99)
    snap = start_draft(
        match_id="m-max-actions",
        players=("p1", "p2"),
        universe_id="u1",
        mode="ranked",
        catalog=catalog,
        rarity_weights=DEFAULT_WEIGHTS,
        dataset_version="ds-1",
        draw_source=source,
    ).snapshot

    accepted_actions = 0
    while snap.status is MatchStatus.ACTIVE:
        actor = snap.active_player_id
        assert actor is not None
        snap = shuffle(snap, player_id=actor, expected_revision=snap.revision, draw_source=source).snapshot
        accepted_actions += 1
        if snap.can_skip():
            snap = skip_character(snap, player_id=actor, expected_revision=snap.revision).snapshot
            accepted_actions += 1
        else:
            role = snap.remaining_roles()[actor][0]
            snap = assign_role(snap, player_id=actor, role=role, expected_revision=snap.revision).snapshot
            accepted_actions += 1
        validate_snapshot_invariants(snap)

    assert snap.status is MatchStatus.COMPLETED
    assert accepted_actions == MAX_ACCEPTED_DRAFT_ACTIONS
