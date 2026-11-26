"""Local CLI demonstration for Kayi Arena Module 3 (Match Resolution — RES-1.0).

Run with:
    python -m scripts.demo_resolution
"""

from __future__ import annotations

from app.engine import CatalogEntry, SeededDrawSource, assign_role, shuffle, start_draft
from app.resolution import (
    RepositoryDatasetReader,
    ResolveRequest,
    resolve_completed_draft,
    resolve_match,
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
from tests.test_resolution_unit_and_worked_examples import _build_fixture_repo


def _print_result(title: str, res) -> None:
    print(f"\n=== {title} ===")
    if not res.ok:
        print(f"REJECTED [{res.error_code.value}]: {res.message}")
        return
    s = res.summary
    print(
        f"Outcome: {res.outcome.value} | Decided by: {res.decided_by.value} "
        f"| Score: {s.wins_player_1}-{s.wins_player_2} (draws={s.draws}) "
        f"| Totals: {s.total_player_1} vs {s.total_player_2} (margin={s.total_margin:+d})"
    )
    for m in res.matchups:
        print(
            f"  {m.role:10s} | P1 {m.player_1.character_id:14s} (P={m.player_1.power}, F={m.player_1.fit}, S={m.player_1.score:3d}) "
            f"vs P2 {m.player_2.character_id:14s} (P={m.player_2.power}, F={m.player_2.fit}, S={m.player_2.score:3d}) "
            f"-> {m.winner.value:8s} ({m.margin:+d})"
        )


def main() -> None:
    print("Kayi Arena — Module 3 Match Resolution Demo (RES-1.0)")

    # 1. Worked examples
    scenarios = [
        ("Example 1: Normal Victory (5-2)", [72, 57, 80, 70, 73, 74, 43], [68, 43, 60, 60, 79, 57, 74]),
        ("Example 2: Victory Despite Lower Total (262 vs 478)", [72, 57, 60, 60, 7, 3, 3], [68, 43, 50, 50, 79, 94, 94]),
        ("Example 4: Combined-Score Tiebreaker (3-3, 453 vs 451)", [100, 43, 90, 80, 54, 43, 43], [68, 57, 70, 60, 79, 74, 43]),
        ("Example 5: Overall Draw (2-2-3, 456 vs 456)", [72, 43, 80, 60, 73, 54, 74], [60, 43, 70, 70, 73, 66, 74]),
    ]
    for title, s1, s2 in scenarios:
        reader, req = _build_fixture_repo(s1, s2)
        _print_result(title, resolve_match(req, reader))

    # 2. Invalid data rejection
    bad_req = ResolveRequest(
        match_id="bad-1",
        universe_id="u1",
        game_mode="ranked",
        starting_player="player_1",
        dataset_version="ds-worked",
        players={"player_1": "p1", "player_2": "p2"},
        teams={"player_1": {"Captain": "x"}, "player_2": {}},
    )
    _print_result("Invalid Role Rejection", resolve_match(bad_req, reader))

    # 3. End-to-end synthetic Module 1 draft + Module 2 dataset + Module 3 resolution
    repo = InMemoryDatasetRepository()
    raw = [
        {"character_id": f"char_{i:02d}", "power": (i % 5) + 1, "fit": {r: (i + j) % 6 for j, r in enumerate(SCORING_ROLES)}}
        for i in range(16)
    ]
    batch = score_batch(raw, SCORE_1_0_CONFIG)
    recs = tuple(
        DatasetRecord(o.character_id, o.power, o.fit, o.scores, RecordStatus.APPROVED, f"rev-{o.character_id}", SCORE_1_0_VERSION)
        for o in batch.results
    )
    repo.publish(
        build_signed_manifest(
            dataset_version="demo-ds-1",
            kind=DatasetKind.PRODUCTION,
            config=SCORE_1_0_CONFIG,
            records=recs,
            governing_versions=GoverningVersions("UP-1", "A-1", "C-1"),
            created_at="2026-11-26T00:00:00Z",
        ),
        config=SCORE_1_0_CONFIG,
    )
    src = SeededDrawSource(seed=42)
    snap = start_draft(
        match_id="demo-e2e",
        players=("Alice", "Bob"),
        universe_id="demo-uni",
        mode="friendly",
        catalog=tuple(CatalogEntry(r.character_id, "Epic") for r in recs),
        rarity_weights={"Epic": 100.0},
        dataset_version="demo-ds-1",
        draw_source=src,
    ).snapshot
    completed = None
    while snap.active_player_id is not None:
        actor = snap.active_player_id
        snap = shuffle(snap, player_id=actor, expected_revision=snap.revision, draw_source=src).snapshot
        res = assign_role(snap, player_id=actor, role=snap.remaining_roles()[actor][0], expected_revision=snap.revision)
        snap = res.snapshot
        completed = res.completed_output

    _print_result(
        "End-to-End Synthetic Draft + Resolution",
        resolve_completed_draft(completed, RepositoryDatasetReader(repo), player_order=("Alice", "Bob")),
    )


if __name__ == "__main__":
    main()
