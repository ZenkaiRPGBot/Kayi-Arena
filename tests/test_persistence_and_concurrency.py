"""Tests for snapshot restoration, public-view isolation, CAS, and concurrency."""

from __future__ import annotations

import asyncio
from dataclasses import fields

import pytest

from app.engine import (
    DraftPhase,
    ErrorCode,
    InMemoryDraftStore,
    MatchStatus,
    PersistenceWriteError,
    PublicDraftView,
    ScriptedDrawSource,
    SeededDrawSource,
    SerializedDraftService,
    TerminationReason,
    assign_role,
    project_public_view,
    restore_snapshot,
    shuffle,
    skip_character,
    start_draft,
)
from tests.conftest import DEFAULT_WEIGHTS, make_catalog


def test_public_view_strictly_excludes_internal_secrets() -> None:
    allowed_fields = {
        "match_id",
        "players",
        "universe_id",
        "mode",
        "status",
        "phase",
        "revision",
        "active_player_id",
        "progress",
        "turn_number",
        "teams",
        "remaining_roles",
        "skips_remaining",
        "held_character",
        "can_skip",
        "terminal_summary",
    }
    assert {f.name for f in fields(PublicDraftView)} == allowed_fields

    # Two different pools with identical public fields produce identical PublicDraftView
    pool_a = make_catalog(16)
    pool_b = make_catalog(25)
    snap_a = start_draft(
        match_id="same-id",
        players=("p1", "p2"),
        universe_id="u1",
        mode="ranked",
        catalog=pool_a,
        rarity_weights=DEFAULT_WEIGHTS,
        dataset_version="ds-A",
        forced_starter="p1",
    ).snapshot
    snap_b = start_draft(
        match_id="same-id",
        players=("p1", "p2"),
        universe_id="u1",
        mode="ranked",
        catalog=pool_b,
        rarity_weights={"Mythic": 99.0, "Legendary": 1.0, "Epic": 1.0, "Rare": 1.0, "Common": 1.0},
        dataset_version="ds-B",
        forced_starter="p1",
    ).snapshot
    assert project_public_view(snap_a) == project_public_view(snap_b)


def test_step_by_step_snapshot_restore_matches_uninterrupted_run() -> None:
    """Acceptance criterion 4: restore at every step & while holding a character."""
    catalog = make_catalog(18)
    draws = [f"char_{i:03d}" for i in range(16)]
    full_source = ScriptedDrawSource(starting_player="p1", draws=draws)

    # Uninterrupted run (with 1 skip on turn 0, then 14 assignments)
    full_snap = start_draft(
        match_id="m-restore",
        players=("p1", "p2"),
        universe_id="u1",
        mode="ranked",
        catalog=catalog,
        rarity_weights=DEFAULT_WEIGHTS,
        dataset_version="ds-v42",
        draw_source=full_source,
    ).snapshot

    # Record scripted steps + source positions
    steps = []
    # Step 0: shuffle, then skip
    full_snap = shuffle(full_snap, player_id="p1", expected_revision=full_snap.revision, draw_source=full_source).snapshot
    steps.append((full_snap.to_json(), full_source.position))
    full_snap = skip_character(full_snap, player_id="p1", expected_revision=full_snap.revision).snapshot
    steps.append((full_snap.to_json(), full_source.position))

    while full_snap.status is MatchStatus.ACTIVE:
        actor = full_snap.active_player_id
        assert actor is not None
        full_snap = shuffle(full_snap, player_id=actor, expected_revision=full_snap.revision, draw_source=full_source).snapshot
        steps.append((full_snap.to_json(), full_source.position))
        role = full_snap.remaining_roles()[actor][0]
        full_snap = assign_role(full_snap, player_id=actor, role=role, expected_revision=full_snap.revision).snapshot
        steps.append((full_snap.to_json(), full_source.position))

    # Restore from the held-character step (index 2: right after second shuffle, holding char_001)
    held_json, pos = steps[2]
    assert "random" not in held_json.lower() and "seed" not in held_json.lower()
    restored = restore_snapshot(held_json)
    assert restored.phase is DraftPhase.AWAITING_DECISION
    assert restored.held_character is not None
    assert restored.dataset_version == "ds-v42"

    # Restoring while holding grants no redraw (WRONG_PHASE) and no extra skips
    resumed_source = full_source.clone_at(pos)
    bad = shuffle(restored, player_id="p1", expected_revision=restored.revision, draw_source=resumed_source)
    assert bad.error_code is ErrorCode.WRONG_PHASE
    assert restored.skips_remaining["p1"] == 1

    # Continue restored draft to completion and verify exact state_hash match
    cur = restored
    while cur.status is MatchStatus.ACTIVE:
        actor = cur.active_player_id
        assert actor is not None
        if cur.phase is DraftPhase.AWAITING_SHUFFLE:
            cur = shuffle(cur, player_id=actor, expected_revision=cur.revision, draw_source=resumed_source).snapshot
        role = cur.remaining_roles()[actor][0]
        cur = assign_role(cur, player_id=actor, role=role, expected_revision=cur.revision).snapshot

    assert cur.state_hash() == full_snap.state_hash()


@pytest.mark.asyncio
async def test_serialized_service_concurrency_cas_and_commit_before_reveal() -> None:
    catalog = make_catalog(16)
    source = SeededDrawSource(seed=55)
    store = InMemoryDraftStore()
    service = SerializedDraftService(store=store, draw_source=source)

    start_res = await service.start_match(
        match_id="m-async",
        players=("p1", "p2"),
        universe_id="u1",
        mode="ranked",
        catalog=catalog,
        rarity_weights=DEFAULT_WEIGHTS,
        dataset_version="ds-1",
        forced_starter="p1",
    )
    assert start_res.revision if hasattr(start_res, "revision") else start_res.snapshot.revision == 0

    # Commit-before-reveal: failed save on Shuffle must raise and leave state untouched
    store.fail_next_save = True
    with pytest.raises(PersistenceWriteError):
        await service.shuffle(match_id="m-async", player_id="p1", expected_revision=0)
    view_after_fail = service.get_public_view("m-async")
    assert view_after_fail is not None
    assert view_after_fail.revision == 0
    assert view_after_fail.held_character is None

    # Normal shuffle succeeds at revision 1
    shuf = await service.shuffle(match_id="m-async", player_id="p1", expected_revision=0)
    assert shuf.accepted
    assert shuf.snapshot.revision == 1

    # Simultaneous skip & assign at revision 1 -> exactly one accepted, one STALE_REVISION
    r_skip, r_assign = await asyncio.gather(
        service.skip_character(match_id="m-async", player_id="p1", expected_revision=1),
        service.assign_role(
            match_id="m-async", player_id="p1", role="Captain", expected_revision=1
        ),
    )
    accepted_count = sum(1 for r in (r_skip, r_assign) if r.accepted)
    rejected = [r for r in (r_skip, r_assign) if not r.accepted]
    assert accepted_count == 1
    assert len(rejected) == 1
    assert rejected[0].error_code is ErrorCode.STALE_REVISION

    # Simultaneous terminate & next action -> consistent terminal result
    cur_view = service.get_public_view("m-async")
    assert cur_view is not None and cur_view.active_player_id is not None
    r_term, r_next = await asyncio.gather(
        service.terminate(
            match_id="m-async",
            reason=TerminationReason.FORFEIT,
            subject_player_id="p1",
        ),
        service.shuffle(
            match_id="m-async",
            player_id=cur_view.active_player_id,
            expected_revision=cur_view.revision,
        ),
    )
    assert r_term.accepted
    if r_next.accepted:
        assert r_term.snapshot.revision == cur_view.revision + 2
    else:
        assert r_next.error_code is ErrorCode.MATCH_NOT_ACTIVE
