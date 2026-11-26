"""Negative validation, precedence, no-dataset-access, and M1-M2-M3 integration tests."""

from __future__ import annotations

import pytest

from app.engine import (
    CatalogEntry,
    SeededDrawSource,
    assign_role,
    shuffle,
    start_draft,
)
from app.resolution import (
    DatasetUnavailableError,
    MatchOutcome,
    RepositoryDatasetReader,
    ResolutionErrorCode,
    ResolveRequest,
    resolve_completed_draft,
    resolve_match,
)
from app.scoring import (
    DatasetKind,
    DatasetManifest,
    DatasetRecord,
    GoverningVersions,
    InMemoryDatasetRepository,
    RecordStatus,
    RoleWeight,
    SCORE_1_0_CONFIG,
    SCORE_1_0_PERCENT_WEIGHTS,
    SCORE_1_0_VERSION,
    SCORING_ROLES,
    ScoringConfig,
    build_signed_manifest,
    score_batch,
)
from tests.conftest import DEFAULT_WEIGHTS

_GOV = GoverningVersions("UP-1", "A-1", "C-1")


class _SpyDatasetReader:
    """Fails test if Stages 1-4 ever touch dataset reader, or injects faults."""

    def __init__(self, inner=None, *, fail_unavailable: bool = False) -> None:
        self.inner = inner
        self.fail_unavailable = fail_unavailable
        self.calls = 0

    def load_manifest(self, dataset_version: str):
        self.calls += 1
        if self.fail_unavailable:
            raise DatasetUnavailableError("transient backend timeout")
        return self.inner.load_manifest(dataset_version)

    def get_character(self, dataset_version: str, character_id: str):
        self.calls += 1
        if self.fail_unavailable:
            raise DatasetUnavailableError("transient backend timeout")
        return self.inner.get_character(dataset_version, character_id)


def _valid_raw_request(ds_version: str = "ds-val") -> dict:
    return {
        "match_id": "m-1",
        "universe_id": "u-1",
        "game_mode": "ranked",
        "starting_player": "player_1",
        "dataset_version": ds_version,
        "players": {"player_1": "p1", "player_2": "p2"},
        "teams": {
            "player_1": {r: f"c1_{r}" for r in SCORING_ROLES},
            "player_2": {r: f"c2_{r}" for r in SCORING_ROLES},
        },
    }


def _repo_with_valid_14(ds_version: str = "ds-val") -> InMemoryDatasetRepository:
    raw = [
        {"character_id": cid, "power": 3, "fit": {r: 2 for r in SCORING_ROLES}}
        for slot in ("c1", "c2")
        for cid in (f"{slot}_{r}" for r in SCORING_ROLES)
    ]
    batch = score_batch(raw, SCORE_1_0_CONFIG)
    recs = tuple(
        DatasetRecord(out.character_id, out.power, out.fit, out.scores, RecordStatus.APPROVED, f"rev-{out.character_id}", SCORE_1_0_VERSION)
        for out in batch.results
    )
    repo = InMemoryDatasetRepository()
    repo.publish(
        build_signed_manifest(
            dataset_version=ds_version,
            kind=DatasetKind.PRODUCTION,
            config=SCORE_1_0_CONFIG,
            records=recs,
            governing_versions=_GOV,
            created_at="2026-11-26T00:00:00Z",
        ),
        config=SCORE_1_0_CONFIG,
    )
    return repo


def test_stages_1_to_4_never_access_dataset_and_follow_precedence() -> None:
    spy = _SpyDatasetReader()

    # Stage 1: MALFORMED_REQUEST (beats Stage 2 invalid role & Stage 4 duplicate)
    req_s1 = _valid_raw_request()
    req_s1["teams"]["player_1"][123] = "x"  # non-string key
    req_s1["teams"]["player_2"]["bogus"] = "c1_captain"
    r1 = resolve_match(req_s1, spy)
    assert not r1.ok and r1.error_code is ResolutionErrorCode.MALFORMED_REQUEST
    assert not r1.retryable

    # Stage 1: invalid game mode, identical players, null/empty char id
    for mut in (
        lambda d: d.update({"game_mode": "turbo"}),
        lambda d: d["players"].update({"player_2": "p1"}),
        lambda d: d["teams"]["player_1"].update({"captain": ""}),
        lambda d: d.pop("match_id"),
    ):
        bad = _valid_raw_request()
        mut(bad)
        res = resolve_match(bad, spy)
        assert not res.ok and res.error_code is ResolutionErrorCode.MALFORMED_REQUEST

    # Stage 2: INVALID_ROLE (capitalization / whitespace not silently normalized; beats Stage 3 & 4)
    req_s2 = _valid_raw_request()
    del req_s2["teams"]["player_1"]["captain"]
    req_s2["teams"]["player_1"]["Captain"] = "c1_captain"
    r2 = resolve_match(req_s2, spy)
    assert not r2.ok and r2.error_code is ResolutionErrorCode.INVALID_ROLE

    # Stage 3: INCOMPLETE_TEAM (beats Stage 4 duplicate)
    req_s3 = _valid_raw_request()
    del req_s3["teams"]["player_1"]["healer"]
    req_s3["teams"]["player_2"]["captain"] = "c1_captain"  # duplicate
    r3 = resolve_match(req_s3, spy)
    assert not r3.ok and r3.error_code is ResolutionErrorCode.INCOMPLETE_TEAM

    # Stage 4: DUPLICATE_CHARACTER (within or across teams)
    req_s4 = _valid_raw_request()
    req_s4["teams"]["player_2"]["captain"] = "c1_captain"
    r4 = resolve_match(req_s4, spy)
    assert not r4.ok and r4.error_code is ResolutionErrorCode.DUPLICATE_CHARACTER

    assert spy.calls == 0  # Zero dataset calls during Stages 1-4


def test_stages_5_to_9_dataset_and_record_validation() -> None:
    repo = _repo_with_valid_14("ds-val")
    reader = RepositoryDatasetReader(repo)

    # Stage 5: DATASET_NOT_FOUND
    r5 = resolve_match(_valid_raw_request("missing-ds"), reader)
    assert not r5.ok and r5.error_code is ResolutionErrorCode.DATASET_NOT_FOUND
    assert r5.retryable is False

    # Stage 5b: DATASET_UNAVAILABLE (only retryable error)
    r5b = resolve_match(_valid_raw_request(), _SpyDatasetReader(fail_unavailable=True))
    assert not r5b.ok and r5b.error_code is ResolutionErrorCode.DATASET_UNAVAILABLE
    assert r5b.retryable is True
    assert '"error_code":"DATASET_UNAVAILABLE"' in r5b.to_canonical_json()

    # Stage 6: DATASET_INTEGRITY_FAILURE (tampered hash)
    tampered_repo = _repo_with_valid_14("ds-tamper")
    orig = tampered_repo._versions["ds-tamper"]  # noqa: SLF001
    tampered_repo._versions["ds-tamper"] = DatasetManifest(  # noqa: SLF001
        orig.dataset_version, orig.kind, orig.scoring_version, orig.records, orig.governing_versions, "0" * 64, orig.created_at
    )
    r6 = resolve_match(_valid_raw_request("ds-tamper"), RepositoryDatasetReader(tampered_repo))
    assert not r6.ok and r6.error_code is ResolutionErrorCode.DATASET_INTEGRITY_FAILURE

    # Stage 7: UNSUPPORTED_SCORING_VERSION
    w2 = {r: RoleWeight(fp, pp) for r, (fp, pp) in SCORE_1_0_PERCENT_WEIGHTS.items()}
    cfg2 = ScoringConfig("SCORE-2.0", w2)
    recs2 = tuple(
        DatasetRecord(r.character_id, r.power, r.fit, r.scores, RecordStatus.APPROVED, r.revision_ref, "SCORE-2.0")
        for r in orig.records
    )
    repo2 = InMemoryDatasetRepository()
    repo2.publish(
        build_signed_manifest(
            dataset_version="ds-v2",
            kind=DatasetKind.PRODUCTION,
            config=cfg2,
            records=recs2,
            governing_versions=_GOV,
            created_at="2026-11-26T00:00:00Z",
        ),
        config=cfg2,
    )
    r7 = resolve_match(_valid_raw_request("ds-v2"), RepositoryDatasetReader(repo2))
    assert not r7.ok and r7.error_code is ResolutionErrorCode.UNSUPPORTED_SCORING_VERSION

    # Stage 8: CHARACTER_NOT_FOUND
    req_s8 = _valid_raw_request("ds-val")
    req_s8["teams"]["player_2"]["healer"] = "unknown_char"
    r8 = resolve_match(req_s8, reader)
    assert not r8.ok and r8.error_code is ResolutionErrorCode.CHARACTER_NOT_FOUND

    # Stage 9: CHARACTER_RECORD_INVALID (float, bool, wrong ID, tampered stored score)
    class _MutatedRecordReader:
        def __init__(self, manifest, bad_id: str, bad_record):
            self._manifest = manifest
            self._bad_id = bad_id
            self._bad_record = bad_record

        def load_manifest(self, dataset_version: str):
            return self._manifest

        def get_character(self, dataset_version: str, character_id: str):
            if character_id == self._bad_id:
                return self._bad_record
            return reader.get_character(dataset_version, character_id)

    valid_manifest = repo.load_version("ds-val")
    good_rec = reader.get_character("ds-val", "c1_captain")
    for bad_rec in (
        DatasetRecord("wrong_id", good_rec.power, good_rec.fit, good_rec.scores, RecordStatus.APPROVED, "r", SCORE_1_0_VERSION),
        DatasetRecord("c1_captain", 3.0, good_rec.fit, good_rec.scores, RecordStatus.APPROVED, "r", SCORE_1_0_VERSION),  # type: ignore[arg-type]
        DatasetRecord("c1_captain", True, good_rec.fit, good_rec.scores, RecordStatus.APPROVED, "r", SCORE_1_0_VERSION),  # type: ignore[arg-type]
        DatasetRecord("c1_captain", good_rec.power, good_rec.fit, {**dict(good_rec.scores), "captain": 99}, RecordStatus.APPROVED, "r", SCORE_1_0_VERSION),
    ):
        r9 = resolve_match(_valid_raw_request("ds-val"), _MutatedRecordReader(valid_manifest, "c1_captain", bad_rec))
        assert not r9.ok and r9.error_code is ResolutionErrorCode.CHARACTER_RECORD_INVALID


def test_end_to_end_module1_draft_to_module2_dataset_to_module3_resolution() -> None:
    """Full pipeline integration: M2 publish v1 -> M1 draft -> M3 resolve -> M2 publish v2 -> v1 unchanged."""
    repo = InMemoryDatasetRepository()
    raw = [
        {"character_id": f"hero_{i:02d}", "power": (i % 5) + 1, "fit": {r: (i + idx) % 6 for idx, r in enumerate(SCORING_ROLES)}}
        for i in range(18)
    ]
    batch_v1 = score_batch(raw, SCORE_1_0_CONFIG)
    recs_v1 = tuple(
        DatasetRecord(out.character_id, out.power, out.fit, out.scores, RecordStatus.APPROVED, f"rev-{out.character_id}", SCORE_1_0_VERSION)
        for out in batch_v1.results
    )
    repo.publish(
        build_signed_manifest(
            dataset_version="ds-e2e-v1",
            kind=DatasetKind.PRODUCTION,
            config=SCORE_1_0_CONFIG,
            records=recs_v1,
            governing_versions=_GOV,
            created_at="2026-11-26T00:00:00Z",
        ),
        config=SCORE_1_0_CONFIG,
    )

    # Run Module 1 seeded draft
    catalog = tuple(CatalogEntry(r.character_id, "Rare") for r in recs_v1)
    src = SeededDrawSource(seed=2026)
    snap = start_draft(
        match_id="e2e-001",
        players=("alice", "bob"),
        universe_id="uni-e2e",
        mode="ranked",
        catalog=catalog,
        rarity_weights={"Rare": 100.0},
        dataset_version="ds-e2e-v1",
        draw_source=src,
    ).snapshot

    completed_output = None
    while snap.active_player_id is not None:
        actor = snap.active_player_id
        snap = shuffle(snap, player_id=actor, expected_revision=snap.revision, draw_source=src).snapshot
        role = snap.remaining_roles()[actor][0]
        res = assign_role(snap, player_id=actor, role=role, expected_revision=snap.revision)
        snap = res.snapshot
        completed_output = res.completed_output

    assert completed_output is not None
    reader = RepositoryDatasetReader(repo)
    resolved_v1 = resolve_completed_draft(completed_output, reader, player_order=("alice", "bob"))
    assert resolved_v1.ok is True
    assert resolved_v1.dataset_version == "ds-e2e-v1"
    assert resolved_v1.players["player_1"] == "alice"
    assert resolved_v1.players["player_2"] == "bob"
    assert len({p.character_id for m in resolved_v1.matchups for p in (m.player_1, m.player_2)}) == 14

    # Publish v2 with altered ratings; resolving the match pinned to v1 must return identical bytes
    raw_v2 = [{"character_id": f"hero_{i:02d}", "power": 5, "fit": {r: 5 for r in SCORING_ROLES}} for i in range(18)]
    batch_v2 = score_batch(raw_v2, SCORE_1_0_CONFIG)
    recs_v2 = tuple(
        DatasetRecord(out.character_id, out.power, out.fit, out.scores, RecordStatus.APPROVED, f"rev2-{out.character_id}", SCORE_1_0_VERSION)
        for out in batch_v2.results
    )
    repo.publish(
        build_signed_manifest(
            dataset_version="ds-e2e-v2",
            kind=DatasetKind.PRODUCTION,
            config=SCORE_1_0_CONFIG,
            records=recs_v2,
            governing_versions=_GOV,
            created_at="2026-11-26T01:00:00Z",
            predecessor_version="ds-e2e-v1",
        ),
        config=SCORE_1_0_CONFIG,
    )
    resolved_again = resolve_completed_draft(completed_output, reader, player_order=("alice", "bob"))
    assert resolved_again.to_canonical_bytes() == resolved_v1.to_canonical_bytes()
