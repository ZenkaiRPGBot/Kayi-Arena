"""Property tests, invariants I1-I9, canonical JSON, and 1,000+ replays for Module 3."""

from __future__ import annotations

import copy
import random

from app.resolution import (
    DecidedBy,
    MatchOutcome,
    MatchupWinner,
    RepositoryDatasetReader,
    ResolveRequest,
    resolve_match,
    validate_resolution_invariants,
)
from app.scoring import (
    DatasetKind,
    DatasetRecord,
    GoverningVersions,
    InMemoryDatasetRepository,
    RecordStatus,
    SCORE_1_0_CONFIG,
    SCORE_1_0_VERSION,
    SCORING_ROLES,
    build_signed_manifest,
    score_batch,
)

_GOV = GoverningVersions("UP-1", "A-1", "C-1")


def _make_seeded_repo(seed: int, size: int = 24) -> tuple[InMemoryDatasetRepository, list[str]]:
    rng = random.Random(seed)
    raw = [
        {
            "character_id": f"char_{i:03d}",
            "power": rng.randint(1, 5),
            "fit": {r: rng.randint(0, 5) for r in SCORING_ROLES},
        }
        for i in range(size)
    ]
    batch = score_batch(raw, SCORE_1_0_CONFIG)
    assert batch.accepted
    recs = tuple(
        DatasetRecord(
            out.character_id,
            out.power,
            out.fit,
            out.scores,
            RecordStatus.APPROVED,
            f"rev-{out.character_id}",
            SCORE_1_0_VERSION,
        )
        for out in batch.results
    )
    repo = InMemoryDatasetRepository()
    repo.publish(
        build_signed_manifest(
            dataset_version=f"ds-{seed}",
            kind=DatasetKind.PRODUCTION,
            config=SCORE_1_0_CONFIG,
            records=recs,
            governing_versions=_GOV,
            created_at="2026-11-26T00:00:00Z",
        ),
        config=SCORE_1_0_CONFIG,
    )
    return repo, [r.character_id for r in recs]


def test_1000_seeded_replays_invariants_symmetry_and_canonical_json() -> None:
    repo, cids = _make_seeded_repo(20261126, size=30)
    reader = RepositoryDatasetReader(repo)
    rng = random.Random(999)

    for i in range(1000):
        chosen = rng.sample(cids, 14)
        p1_team = {r: chosen[idx] for idx, r in enumerate(SCORING_ROLES)}
        p2_team = {r: chosen[7 + idx] for idx, r in enumerate(SCORING_ROLES)}
        starter = "player_1" if i % 2 == 0 else "player_2"
        mode = "ranked" if i % 2 == 0 else "friendly"

        req = ResolveRequest(
            match_id=f"m-{i}",
            universe_id="uni-prop",
            game_mode=mode,
            starting_player=starter,
            dataset_version="ds-20261126",
            players={"player_1": f"alice_{i}", "player_2": f"bob_{i}"},
            teams={"player_1": p1_team, "player_2": p2_team},
        )
        res = resolve_match(req, reader)
        assert res.ok is True
        validate_resolution_invariants(res)

        # Equal victory counts require odd drawn-matchup count (I7)
        if res.summary.wins_player_1 == res.summary.wins_player_2:
            assert res.summary.draws in (1, 3, 5, 7)

        # Deterministic replay -> byte-identical canonical JSON
        res2 = resolve_match(req, reader)
        raw_bytes = res.to_canonical_bytes()
        assert raw_bytes == res2.to_canonical_bytes()
        raw_str = res.to_canonical_json()
        assert not raw_str.endswith("\n")
        assert "null" not in raw_str
        assert ": " not in raw_str and ", " not in raw_str

        # Sample player-swapping symmetry (I8) and Ranked/Friendly equivalence (I9)
        if i < 200:
            swapped_starter = "player_2" if starter == "player_1" else "player_1"
            swapped = ResolveRequest(
                match_id=f"m-{i}",
                universe_id="uni-prop",
                game_mode="friendly" if mode == "ranked" else "ranked",
                starting_player=swapped_starter,
                dataset_version="ds-20261126",
                players={"player_1": f"bob_{i}", "player_2": f"alice_{i}"},
                teams={"player_1": p2_team, "player_2": p1_team},
            )
            s_res = resolve_match(swapped, reader)
            assert s_res.ok is True
            assert s_res.decided_by is res.decided_by
            assert s_res.summary.wins_player_1 == res.summary.wins_player_2
            assert s_res.summary.wins_player_2 == res.summary.wins_player_1
            assert s_res.summary.total_margin == -res.summary.total_margin
            if res.outcome is MatchOutcome.PLAYER_1_WIN:
                assert s_res.outcome is MatchOutcome.PLAYER_2_WIN
            elif res.outcome is MatchOutcome.PLAYER_2_WIN:
                assert s_res.outcome is MatchOutcome.PLAYER_1_WIN
            else:
                assert s_res.outcome is MatchOutcome.DRAW
                assert s_res.decided_by is DecidedBy.NONE


def test_role_order_identity_independence_unicode_and_no_input_mutation() -> None:
    repo, cids = _make_seeded_repo(77, size=20)
    reader = RepositoryDatasetReader(repo)

    p1_team = {r: cids[idx] for idx, r in enumerate(SCORING_ROLES)}
    p2_team = {r: cids[7 + idx] for idx, r in enumerate(SCORING_ROLES)}

    # Reversed dict key insertion order & different player/match IDs + Unicode
    req_a = {
        "match_id": "match-α",
        "universe_id": "uni-Ω",
        "game_mode": "ranked",
        "starting_player": "player_1",
        "dataset_version": "ds-77",
        "players": {"player_1": "P1_α", "player_2": "P2_β"},
        "teams": {"player_1": dict(p1_team), "player_2": dict(p2_team)},
    }
    req_b = {
        "match_id": "match-other",
        "universe_id": "uni-other",
        "game_mode": "friendly",
        "starting_player": "player_2",
        "dataset_version": "ds-77",
        "players": {"player_2": "renamed_2", "player_1": "renamed_1"},
        "teams": {
            "player_2": {r: p2_team[r] for r in reversed(SCORING_ROLES)},
            "player_1": {r: p1_team[r] for r in reversed(SCORING_ROLES)},
        },
    }
    snap_a = copy.deepcopy(req_a)

    res_a = resolve_match(req_a, reader)
    res_b = resolve_match(req_b, reader)
    assert req_a == snap_a  # zero input mutation
    assert res_a.ok and res_b.ok
    assert res_a.outcome is res_b.outcome
    assert res_a.decided_by is res_b.decided_by
    assert res_a.summary == res_b.summary
    # Unicode preserved directly in UTF-8 without \uXXXX escaping
    assert "match-α" in res_a.to_canonical_json()
    assert "\\u" not in res_a.to_canonical_json()
