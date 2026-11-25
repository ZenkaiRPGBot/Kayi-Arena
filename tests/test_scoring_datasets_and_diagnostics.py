"""T10-T12 tests: dataset integrity, historical replay, and advisory diagnostics."""

from __future__ import annotations

import math

import pytest

from app.scoring import (
    DatasetErrorCode,
    DatasetKind,
    DatasetManifest,
    DatasetRecord,
    DatasetValidationError,
    GoverningVersions,
    InMemoryDatasetRepository,
    RecordStatus,
    RoleWeight,
    SCORE_1_0_CONFIG,
    SCORE_1_0_PERCENT_WEIGHTS,
    SCORING_ROLES,
    ScoringConfig,
    build_signed_manifest,
    compute_diagnostics,
    score_batch,
)
from tests.test_scoring_engine import _NARUTO_FIXTURES

_GOV = GoverningVersions(
    universe_policy_version="UP-1.0",
    anchor_set_version="ANCHOR-1.0",
    calibration_set_version="CAL-1.0",
)


def _make_dataset_records(
    items: list[tuple[str, int, dict[str, int]]],
    *,
    config: ScoringConfig = SCORE_1_0_CONFIG,
    status: RecordStatus = RecordStatus.APPROVED,
) -> tuple[DatasetRecord, ...]:
    batch = score_batch(
        [{"character_id": cid, "power": p, "fit": f} for cid, p, f in items],
        config=config,
    )
    assert batch.accepted
    return tuple(
        DatasetRecord(
            character_id=out.character_id,
            power=out.power,
            fit=out.fit,
            scores=out.scores,
            status=status,
            revision_ref=f"rev-{out.character_id}",
            scoring_version=config.version,
        )
        for out in batch.results
    )


def test_t10_dataset_version_integrity_rules() -> None:
    """T10: DV1, DV2, DV3, DV4, DV7, DV8."""
    repo = InMemoryDatasetRepository()
    recs = _make_dataset_records(
        [("c1", 4, {r: 3 for r in SCORING_ROLES}), ("c2", 2, {r: 1 for r in SCORING_ROLES})]
    )

    # 1. DV1: Draft record in production kind -> blocked
    draft_rec = DatasetRecord(
        character_id="c3",
        power=3,
        fit=recs[0].fit,
        scores=recs[0].scores,
        status=RecordStatus.DRAFT,
        revision_ref="rev-c3",
        scoring_version=SCORE_1_0_CONFIG.version,
    )
    m_draft = build_signed_manifest(
        dataset_version="ds-prod-draft",
        kind=DatasetKind.PRODUCTION,
        config=SCORE_1_0_CONFIG,
        records=(recs[0], draft_rec),
        governing_versions=_GOV,
        created_at="2026-11-25T19:00:00Z",
    )
    with pytest.raises(DatasetValidationError) as exc_dv1:
        repo.publish(m_draft, config=SCORE_1_0_CONFIG)
    assert exc_dv1.value.code is DatasetErrorCode.NON_APPROVED_IN_PRODUCTION

    # 2. DV3: Hash mismatch on publish & on load (fail closed)
    m_valid = build_signed_manifest(
        dataset_version="ds-1",
        kind=DatasetKind.PRODUCTION,
        config=SCORE_1_0_CONFIG,
        records=recs,
        governing_versions=_GOV,
        created_at="2026-11-25T19:00:00Z",
    )
    m_bad_hash = DatasetManifest(
        dataset_version=m_valid.dataset_version,
        kind=m_valid.kind,
        scoring_version=m_valid.scoring_version,
        records=m_valid.records,
        governing_versions=m_valid.governing_versions,
        content_hash="0" * 64,
        created_at=m_valid.created_at,
    )
    with pytest.raises(DatasetValidationError) as exc_dv3:
        repo.publish(m_bad_hash, config=SCORE_1_0_CONFIG)
    assert exc_dv3.value.code is DatasetErrorCode.HASH_MISMATCH

    # Publish valid ds-1, then verify DV2 immutability
    repo.publish(m_valid, config=SCORE_1_0_CONFIG)
    with pytest.raises(DatasetValidationError) as exc_dv2:
        repo.publish(m_valid, config=SCORE_1_0_CONFIG)
    assert exc_dv2.value.code is DatasetErrorCode.VERSION_IMMUTABLE

    # Simulate storage tampering -> DV3 fails closed on load
    repo._versions["ds-1"] = m_bad_hash  # noqa: SLF001
    with pytest.raises(DatasetValidationError) as exc_load:
        repo.load_version("ds-1")
    assert exc_load.value.code is DatasetErrorCode.HASH_MISMATCH

    # 3. DV4: Stored score mismatch -> blocked
    tampered_scores = dict(recs[0].scores)
    tampered_scores["captain"] = 99
    rec_bad_score = DatasetRecord(
        character_id=recs[0].character_id,
        power=recs[0].power,
        fit=recs[0].fit,
        scores=tampered_scores,
        status=RecordStatus.APPROVED,
        revision_ref="rev-bad",
        scoring_version=SCORE_1_0_CONFIG.version,
    )
    m_bad_score = build_signed_manifest(
        dataset_version="ds-bad-score",
        kind=DatasetKind.PRODUCTION,
        config=SCORE_1_0_CONFIG,
        records=(rec_bad_score,),
        governing_versions=_GOV,
        created_at="2026-11-25T19:00:00Z",
    )
    with pytest.raises(DatasetValidationError) as exc_dv4:
        repo.publish(m_bad_score, config=SCORE_1_0_CONFIG)
    assert exc_dv4.value.code is DatasetErrorCode.SCORE_MISMATCH

    # 4. DV7: Duplicate character_id -> blocked
    m_dup = build_signed_manifest(
        dataset_version="ds-dup",
        kind=DatasetKind.SANDBOX,
        config=SCORE_1_0_CONFIG,
        records=(recs[0], recs[0]),
        governing_versions=_GOV,
        created_at="2026-11-25T19:00:00Z",
    )
    with pytest.raises(DatasetValidationError) as exc_dv7:
        repo.publish(m_dup, config=SCORE_1_0_CONFIG)
    assert exc_dv7.value.code is DatasetErrorCode.DUPLICATE_CHARACTER

    # 5. DV8: Mixed scoring versions -> blocked
    rec_other_ver = DatasetRecord(
        character_id="c9",
        power=recs[0].power,
        fit=recs[0].fit,
        scores=recs[0].scores,
        status=RecordStatus.APPROVED,
        revision_ref="rev-c9",
        scoring_version="SCORE-2.0",
    )
    m_mixed = build_signed_manifest(
        dataset_version="ds-mixed",
        kind=DatasetKind.PRODUCTION,
        config=SCORE_1_0_CONFIG,
        records=(recs[0], rec_other_ver),
        governing_versions=_GOV,
        created_at="2026-11-25T19:00:00Z",
    )
    with pytest.raises(DatasetValidationError) as exc_dv8:
        repo.publish(m_mixed, config=SCORE_1_0_CONFIG)
    assert exc_dv8.value.code is DatasetErrorCode.MIXED_SCORING_VERSION


def test_t11_historical_dataset_retrieval_via_simulated_match_reference() -> None:
    """T11: Match started on A retrieves A's ratings/scoring version after B is published."""
    repo = InMemoryDatasetRepository()

    # Publish version A with SCORE-1.0
    recs_a = _make_dataset_records([("hero_x", 3, {r: 4 for r in SCORING_ROLES})], config=SCORE_1_0_CONFIG)
    manifest_a = build_signed_manifest(
        dataset_version="ds-A",
        kind=DatasetKind.PRODUCTION,
        config=SCORE_1_0_CONFIG,
        records=recs_a,
        governing_versions=_GOV,
        created_at="2026-11-25T18:00:00Z",
    )
    repo.publish(manifest_a, config=SCORE_1_0_CONFIG)

    # Simulated match reference captures opaque dataset_version at draft start
    simulated_match_ref = {"match_id": "m-replay-1", "dataset_version": "ds-A", "char_id": "hero_x"}

    # Later, version B is published with an altered scoring config SCORE-2.0 and changed ratings
    weights_v2 = {
        role: RoleWeight(fp, pp)
        for role, (fp, pp) in SCORE_1_0_PERCENT_WEIGHTS.items()
    }
    weights_v2["attacker"] = RoleWeight(70, 30)
    config_v2 = ScoringConfig(version="SCORE-2.0", weights=weights_v2)
    recs_b = _make_dataset_records([("hero_x", 5, {r: 5 for r in SCORING_ROLES})], config=config_v2)
    manifest_b = build_signed_manifest(
        dataset_version="ds-B",
        kind=DatasetKind.PRODUCTION,
        config=config_v2,
        records=recs_b,
        governing_versions=_GOV,
        created_at="2026-11-25T19:00:00Z",
        predecessor_version="ds-A",
    )
    repo.publish(manifest_b, config=config_v2)

    # Retrieving for the simulated match uses A unchanged
    pinned = repo.get_character_for_resolution(
        simulated_match_ref["dataset_version"], simulated_match_ref["char_id"]
    )
    assert pinned.scoring_version == "SCORE-1.0"
    assert pinned.power == 3
    assert pinned.scores["attacker"] == 70  # 4*10 + 3*10

    latest = repo.get_character_for_resolution("ds-B", "hero_x")
    assert latest.scoring_version == "SCORE-2.0"
    assert latest.power == 5
    assert latest.scores["attacker"] == 100


def test_t12_diagnostics_advisory_r5_revised_and_edge_cases() -> None:
    """T12 & R5 revised: works below 50, single universe, constant/empty safe, advisory only."""
    # 1. Empty dataset: safe, preliminary, None correlations
    empty_report = compute_diagnostics([], universe_count=1)
    assert empty_report.sample_size == 0
    assert empty_report.is_preliminary is True
    assert empty_report.advisory_only is True
    assert all(v is None for v in empty_report.pearson_power_fit.values())
    assert empty_report.mean_high_fit_roles == 0.0

    # 2. Constant-value dataset: undefined Pearson -> None without ZeroDivisionError
    const_batch = score_batch(
        [
            {"character_id": "k1", "power": 3, "fit": {r: 2 for r in SCORING_ROLES}},
            {"character_id": "k2", "power": 3, "fit": {r: 2 for r in SCORING_ROLES}},
        ]
    )
    const_report = compute_diagnostics(const_batch.results, universe_count=1)
    assert const_report.is_preliminary is True
    assert all(v is None for v in const_report.pearson_power_fit.values())
    assert const_report.tie_pair_counts["captain"] == 1

    # 3. 14 Naruto calibration fixtures -> preliminary (<50), single universe allowed, exact tie counts
    naruto_batch = score_batch(
        [
            {"character_id": cid, "power": p, "fit": dict(zip(SCORING_ROLES, fits))}
            for cid, p, fits, _ in _NARUTO_FIXTURES
        ]
    )
    report = compute_diagnostics(naruto_batch.results, universe_count=1)
    assert report.sample_size == 14
    assert report.is_preliminary is True
    assert report.sample_status == "preliminary"
    assert report.advisory_only is True
    assert "preliminary_sample_below_50" in report.advisory_flags
    assert "single_universe_sample" in report.advisory_flags
    # Exact tie pair counts verified against Module 2B §4.5 (total 67 of 637 pairs)
    assert dict(report.tie_pair_counts) == {
        "captain": 10,
        "strategist": 8,
        "attacker": 13,
        "tank": 13,
        "assassin": 9,
        "support": 6,
        "healer": 8,
    }
    assert report.total_tie_pairs == 67
    # Mean roles >= 4: 33 / 14 (2B §4.8)
    assert math.isclose(report.mean_high_fit_roles, 33.0 / 14.0, rel_tol=1e-9)
    # Attacker Pearson ~ 0.87 (2B §4.4)
    assert report.pearson_power_fit["attacker"] is not None
    assert round(report.pearson_power_fit["attacker"], 2) == 0.87

    # 4. >= 50 approved characters marks sample_status = "sufficient", is_preliminary = False
    large_batch = score_batch(
        [
            {"character_id": f"c_{i}", "power": (i % 5) + 1, "fit": {r: (i % 6) for r in SCORING_ROLES}}
            for i in range(50)
        ]
    )
    large_report = compute_diagnostics(large_batch.results, universe_count=1)
    assert large_report.sample_size == 50
    assert large_report.is_preliminary is False
    assert large_report.sample_status == "sufficient"
