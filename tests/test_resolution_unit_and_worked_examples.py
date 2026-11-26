"""Unit tests & all 6 worked examples for Module 3 (Match Resolution — RES-1.0)."""

from __future__ import annotations

import pytest

from app.resolution import (
    DecidedBy,
    MatchOutcome,
    MatchupWinner,
    RESOLUTION_VERSION,
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
    score_record,
)

_GOV = GoverningVersions("UP-1", "A-1", "C-1")

# Mapping from (role, target_score) -> (power, role_fit) for worked examples
_SCORE_PAIR: dict[tuple[str, int], tuple[int, int]] = {
    ("captain", 100): (5, 5),
    ("captain", 72): (3, 4),
    ("captain", 68): (4, 3),
    ("captain", 60): (3, 3),
    ("captain", 8): (1, 0),
    ("strategist", 94): (3, 5),
    ("strategist", 57): (2, 3),
    ("strategist", 43): (3, 2),
    ("strategist", 3): (1, 0),
    ("strategist", 100): (5, 5),
    ("attacker", 90): (4, 5),
    ("attacker", 80): (4, 4),
    ("attacker", 70): (3, 4),
    ("attacker", 60): (3, 3),
    ("attacker", 50): (2, 3),
    ("attacker", 10): (1, 0),
    ("attacker", 100): (5, 5),
    ("tank", 80): (4, 4),
    ("tank", 70): (3, 4),
    ("tank", 60): (3, 3),
    ("tank", 50): (2, 3),
    ("tank", 10): (1, 0),
    ("tank", 100): (5, 5),
    ("assassin", 79): (2, 5),
    ("assassin", 73): (3, 4),
    ("assassin", 54): (4, 2),
    ("assassin", 7): (1, 0),
    ("assassin", 100): (5, 5),
    ("support", 94): (3, 5),
    ("support", 74): (2, 4),
    ("support", 66): (5, 3),
    ("support", 57): (2, 3),
    ("support", 54): (1, 3),
    ("support", 43): (3, 2),
    ("support", 3): (1, 0),
    ("support", 100): (5, 5),
    ("healer", 94): (3, 5),
    ("healer", 74): (2, 4),
    ("healer", 43): (3, 2),
    ("healer", 3): (1, 0),
    ("healer", 100): (5, 5),
}


def _build_fixture_repo(
    p1_scores: list[int],
    p2_scores: list[int],
    *,
    ds_version: str = "ds-worked",
) -> tuple[RepositoryDatasetReader, ResolveRequest]:
    records: list[DatasetRecord] = []
    team1: dict[str, str] = {}
    team2: dict[str, str] = {}

    for idx, (role, s1, s2) in enumerate(zip(SCORING_ROLES, p1_scores, p2_scores)):
        p1_pow, p1_fit = _SCORE_PAIR[(role, s1)]
        p2_pow, p2_fit = _SCORE_PAIR[(role, s2)]
        cid1 = f"p1_{role}_{idx}"
        cid2 = f"p2_{role}_{idx}"
        team1[role] = cid1
        team2[role] = cid2

        for cid, pwr, fit_val, expected_s in ((cid1, p1_pow, p1_fit, s1), (cid2, p2_pow, p2_fit, s2)):
            fit_map = {r: 0 for r in SCORING_ROLES}
            fit_map[role] = fit_val
            out = score_record({"character_id": cid, "power": pwr, "fit": fit_map}, SCORE_1_0_CONFIG)
            assert out.scores[role] == expected_s
            records.append(
                DatasetRecord(
                    character_id=cid,
                    power=out.power,
                    fit=out.fit,
                    scores=out.scores,
                    status=RecordStatus.APPROVED,
                    revision_ref=f"rev-{cid}",
                    scoring_version=SCORE_1_0_VERSION,
                )
            )

    repo = InMemoryDatasetRepository()
    manifest = build_signed_manifest(
        dataset_version=ds_version,
        kind=DatasetKind.PRODUCTION,
        config=SCORE_1_0_CONFIG,
        records=records,
        governing_versions=_GOV,
        created_at="2026-11-26T00:00:00Z",
    )
    repo.publish(manifest, config=SCORE_1_0_CONFIG)
    req = ResolveRequest(
        match_id="match-worked",
        universe_id="uni-1",
        game_mode="ranked",
        starting_player="player_1",
        dataset_version=ds_version,
        players={"player_1": "u-alpha", "player_2": "u-beta"},
        teams={"player_1": team1, "player_2": team2},
    )
    return RepositoryDatasetReader(repo), req


@pytest.mark.parametrize(
    "p1_scores,p2_scores,exp_outcome,exp_decided,exp_w1,exp_w2,exp_draws,exp_t1,exp_t2",
    [
        # Example 1 — Normal victory
        ([72, 57, 80, 70, 73, 74, 43], [68, 43, 60, 60, 79, 57, 74], MatchOutcome.PLAYER_1_WIN, DecidedBy.MATCHUP_COUNT, 5, 2, 0, 469, 441),
        # Example 2 — Victory despite lower total
        ([72, 57, 60, 60, 7, 3, 3], [68, 43, 50, 50, 79, 94, 94], MatchOutcome.PLAYER_1_WIN, DecidedBy.MATCHUP_COUNT, 4, 3, 0, 262, 478),
        # Example 3 — Drawn individual matchups
        ([72, 57, 80, 70, 73, 74, 43], [72, 43, 80, 60, 79, 57, 74], MatchOutcome.PLAYER_1_WIN, DecidedBy.MATCHUP_COUNT, 3, 2, 2, 469, 465),
        # Example 4 — Combined-score tiebreaker
        ([100, 43, 90, 80, 54, 43, 43], [68, 57, 70, 60, 79, 74, 43], MatchOutcome.PLAYER_1_WIN, DecidedBy.COMBINED_SCORE, 3, 3, 1, 453, 451),
        # Example 5 — Overall draw
        ([72, 43, 80, 60, 73, 54, 74], [60, 43, 70, 70, 73, 66, 74], MatchOutcome.DRAW, DecidedBy.NONE, 2, 2, 3, 456, 456),
        # Example 6 — All seven matchups drawn
        ([72, 43, 80, 60, 73, 54, 74], [72, 43, 80, 60, 73, 54, 74], MatchOutcome.DRAW, DecidedBy.NONE, 0, 0, 7, 456, 456),
        # Boundaries: min (44) vs max (700)
        ([8, 3, 10, 10, 7, 3, 3], [100, 100, 100, 100, 100, 100, 100], MatchOutcome.PLAYER_2_WIN, DecidedBy.MATCHUP_COUNT, 0, 7, 0, 44, 700),
    ],
)
def test_worked_examples_and_boundaries(
    p1_scores, p2_scores, exp_outcome, exp_decided, exp_w1, exp_w2, exp_draws, exp_t1, exp_t2
) -> None:
    reader, req = _build_fixture_repo(p1_scores, p2_scores)
    res = resolve_match(req, reader)
    assert res.ok is True
    validate_resolution_invariants(res)
    assert res.resolution_version == RESOLUTION_VERSION
    assert res.scoring_version == SCORE_1_0_VERSION
    assert res.outcome is exp_outcome
    assert res.decided_by is exp_decided
    assert res.summary.wins_player_1 == exp_w1
    assert res.summary.wins_player_2 == exp_w2
    assert res.summary.draws == exp_draws
    assert res.summary.total_player_1 == exp_t1
    assert res.summary.total_player_2 == exp_t2
    assert res.summary.total_margin == exp_t1 - exp_t2


def test_player_2_wins_by_combined_score_tiebreaker() -> None:
    reader, req = _build_fixture_repo(
        [68, 57, 70, 60, 79, 74, 43],
        [100, 43, 90, 80, 54, 43, 43],
    )
    res = resolve_match(req, reader)
    assert res.ok is True
    validate_resolution_invariants(res)
    assert res.outcome is MatchOutcome.PLAYER_2_WIN
    assert res.decided_by is DecidedBy.COMBINED_SCORE
    assert res.summary.total_margin == -2


def test_equal_score_with_different_power_and_fit_produces_draw() -> None:
    """Attacker: Fit=4, Power=4 (80) vs Fit=5, Power=3 (80) -> Draw (no tiebreak by Power/Fit)."""
    recs = []
    for cid, pwr, fit_val in (("c_a1", 4, 4), ("c_a2", 3, 5)):
        f = {r: 0 for r in SCORING_ROLES}
        f["attacker"] = fit_val
        out = score_record({"character_id": cid, "power": pwr, "fit": f}, SCORE_1_0_CONFIG)
        assert out.scores["attacker"] == 80
        recs.append(
            DatasetRecord(cid, out.power, out.fit, out.scores, RecordStatus.APPROVED, f"rev-{cid}", SCORE_1_0_VERSION)
        )
    for i in range(12):
        cid = f"filler_{i}"
        f = {r: 2 for r in SCORING_ROLES}
        out = score_record({"character_id": cid, "power": 3, "fit": f}, SCORE_1_0_CONFIG)
        recs.append(
            DatasetRecord(cid, out.power, out.fit, out.scores, RecordStatus.APPROVED, f"rev-{cid}", SCORE_1_0_VERSION)
        )
    repo = InMemoryDatasetRepository()
    repo.publish(
        build_signed_manifest(
            dataset_version="ds-eq",
            kind=DatasetKind.PRODUCTION,
            config=SCORE_1_0_CONFIG,
            records=recs,
            governing_versions=_GOV,
            created_at="2026-11-26T00:00:00Z",
        ),
        config=SCORE_1_0_CONFIG,
    )
    req = ResolveRequest(
        match_id="m-eq",
        universe_id="u1",
        game_mode="friendly",
        starting_player="player_2",
        dataset_version="ds-eq",
        players={"player_1": "p1", "player_2": "p2"},
        teams={
            "player_1": {"captain": "filler_0", "strategist": "filler_1", "attacker": "c_a1", "tank": "filler_2", "assassin": "filler_3", "support": "filler_4", "healer": "filler_5"},
            "player_2": {"captain": "filler_6", "strategist": "filler_7", "attacker": "c_a2", "tank": "filler_8", "assassin": "filler_9", "support": "filler_10", "healer": "filler_11"},
        },
    )
    res = resolve_match(req, RepositoryDatasetReader(repo))
    assert res.ok is True
    attacker_matchup = res.matchups[2]
    assert attacker_matchup.role == "attacker"
    assert attacker_matchup.winner is MatchupWinner.DRAW
    assert attacker_matchup.player_1.power == 4 and attacker_matchup.player_1.fit == 4
    assert attacker_matchup.player_2.power == 3 and attacker_matchup.player_2.fit == 5
    assert res.outcome is MatchOutcome.DRAW
