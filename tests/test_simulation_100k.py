"""Large-scale randomized simulation verifying all 14 invariants across 100,000 drafts."""

from __future__ import annotations

import os
import random
from concurrent.futures import ProcessPoolExecutor

from app.engine import (
    MAX_ACCEPTED_DRAFT_ACTIONS,
    MatchStatus,
    SeededDrawSource,
    assign_role,
    shuffle,
    skip_character,
    start_draft,
    validate_snapshot_invariants,
)
from tests.conftest import DEFAULT_WEIGHTS, make_catalog


def _run_simulation_chunk(args: tuple[int, int, int]) -> int:
    start_idx, count, seed_offset = args
    pool_cache = {size: make_catalog(size) for size in (14, 15, 20, 45, 100, 200)}
    pool_sizes = tuple(pool_cache.keys())
    rng = random.Random(20261125 + seed_offset)
    draw_source = SeededDrawSource(seed=1337 + seed_offset)

    max_actions_seen = 0
    for idx in range(start_idx, start_idx + count):
        pool_size = pool_sizes[idx % len(pool_sizes)]
        policy = idx % 3  # 0: never skip, 1: always skip when legal, 2: random skip
        snap = start_draft(
            match_id=f"sim-{idx}",
            players=("p1", "p2"),
            universe_id="sim",
            mode="ranked",
            catalog=pool_cache[pool_size],
            rarity_weights=DEFAULT_WEIGHTS,
            dataset_version="sim-v1",
            draw_source=draw_source,
        ).snapshot

        accepted_actions = 0
        while snap.status is MatchStatus.ACTIVE:
            actor = snap.active_player_id
            assert actor is not None

            prev_rev = snap.revision
            snap = shuffle(
                snap,
                player_id=actor,
                expected_revision=snap.revision,
                draw_source=draw_source,
            ).snapshot
            accepted_actions += 1
            assert snap.revision == prev_rev + 1

            do_skip = False
            if snap.can_skip():
                if policy == 1:
                    do_skip = True
                elif policy == 2:
                    do_skip = rng.random() < 0.5

            prev_rev = snap.revision
            if do_skip:
                res = skip_character(snap, player_id=actor, expected_revision=snap.revision)
            else:
                roles = snap.remaining_roles()[actor]
                chosen_role = rng.choice(roles)
                res = assign_role(
                    snap,
                    player_id=actor,
                    role=chosen_role,
                    expected_revision=snap.revision,
                )
            assert res.accepted
            snap = res.snapshot
            accepted_actions += 1
            assert snap.revision == prev_rev + 1
            assert accepted_actions <= MAX_ACCEPTED_DRAFT_ACTIONS

            if pool_size == 14 or snap.status is MatchStatus.COMPLETED:
                validate_snapshot_invariants(snap)

        validate_snapshot_invariants(snap)
        assert snap.status is MatchStatus.COMPLETED
        assert len(snap.teams["p1"]) == 7
        assert len(snap.teams["p2"]) == 7
        if accepted_actions > max_actions_seen:
            max_actions_seen = accepted_actions

    return max_actions_seen


def test_100k_randomized_draft_simulations() -> None:
    """Acceptance criteria 1 & 7: >= 100,000 drafts, zero violations, zero deadlocks."""
    total_drafts = 100_000
    workers = min(4, max(1, os.cpu_count() or 1))
    chunk_size = total_drafts // workers
    tasks = [
        (
            w * chunk_size,
            chunk_size if w < workers - 1 else total_drafts - w * chunk_size,
            w,
        )
        for w in range(workers)
    ]

    with ProcessPoolExecutor(max_workers=workers) as pool:
        max_actions = max(pool.map(_run_simulation_chunk, tasks))

    assert max_actions <= MAX_ACCEPTED_DRAFT_ACTIONS
