"""Tests for Module 4A (Database Foundation) and integration with Modules 1-3."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.database import (
    CharacterDatabase,
    DatabaseError,
    DatabaseErrorCode,
    EvaluationStatus,
    EvidenceItem,
    IMPORT_FORMAT_VERSION,
    ImageMetadata,
    ImageValidationStatus,
    RARITY_TIERS,
    SpeciesKind,
    export_published_dataset,
    export_universe_bundle,
    import_catalogue_batch,
    import_evaluation_batch,
)
from app.engine import SeededDrawSource, assign_role, shuffle, start_draft
from app.resolution import ResolutionErrorCode, resolve_completed_draft, resolve_match
from app.scoring import DatasetErrorCode, DatasetKind, DatasetValidationError, SCORING_ROLES


def _verified_image(cid: str) -> ImageMetadata:
    return ImageMetadata(
        url_or_ref=f"assets/{cid}.png",
        source_ref="canon-vol-1",
        mime_type="image/png",
        width=512,
        height=512,
        checksum=f"sha256-{cid}",
        status=ImageValidationStatus.VERIFIED,
    )


def _populate_approved_universe(
    db: CharacterDatabase,
    universe_id: str = "uni_alpha",
    count: int = 16,
    *,
    healer_fit: int = 0,
) -> list[str]:
    db.create_universe(universe_id, f"Universe {universe_id}", min_pool_size=14)
    cids: list[str] = []
    for i in range(count):
        cid = f"{universe_id}_char_{i:02d}"
        rarity = RARITY_TIERS[i % len(RARITY_TIERS)]
        species = SpeciesKind.NON_HUMAN if i % 4 == 0 else SpeciesKind.HUMAN
        fit = {r: (i + idx) % 6 for idx, r in enumerate(SCORING_ROLES)}
        fit["healer"] = healer_fit
        db.add_character(
            character_id=cid,
            universe_id=universe_id,
            name=f"Hero {i}",
            aliases=(f"Alias_{i}",),
            species=species,
            canonical_version=f"Arc {i % 3 + 1}",
            rarity=rarity,
            power=(i % 5) + 1,
            fit=fit,
            evidence=(EvidenceItem("power", "A", "ch-1", "Shown in duel"),),
            source_references=("ch-1",),
            image=_verified_image(cid),
            status=EvaluationStatus.DRAFT,
        )
        db.submit_for_review(cid)
        db.approve_character(cid)
        cids.append(cid)
    return cids


def test_sqlite_persistence_across_reopen_and_multiple_universes(tmp_path: Path) -> None:
    db_file = tmp_path / "kayi_arena.db"
    with CharacterDatabase(db_file) as db:
        _populate_approved_universe(db, "uni_1", count=14)
        _populate_approved_universe(db, "uni_2", count=14)
        db.set_universe_active("uni_2", False)
        manifest, report = db.publish_dataset("uni_1", "uni_1-v1")
        assert report.total_characters == 14
        assert report.advisory_only is True
        assert manifest.dataset_version == "uni_1-v1"

    # Reopen from disk and verify everything persisted + hash passes
    with CharacterDatabase(db_file) as db2:
        active = db2.list_universes(active_only=True)
        assert [u.universe_id for u in active] == ["uni_1"]
        loaded = db2.load_manifest("uni_1-v1")
        assert len(loaded.records) == 14
        rec = db2.get_character("uni_1-v1", "uni_1_char_00")
        assert rec.character_id == "uni_1_char_00"
        entry = db2.get_character_entry("uni_1_char_00")
        assert entry.species is SpeciesKind.NON_HUMAN
        assert entry.aliases == ("Alias_0",)


def test_lifecycle_validation_and_publication_safeguards() -> None:
    db = CharacterDatabase()
    db.create_universe("u1", "Test Uni", min_pool_size=15)

    # Duplicate universe rejected
    with pytest.raises(DatabaseError) as e_u:
        db.create_universe("u1", "Dup")
    assert e_u.value.code is DatabaseErrorCode.UNIVERSE_EXISTS

    # Invalid min_pool_size (< 14) rejected
    with pytest.raises(DatabaseError) as e_min:
        db.create_universe("u_small", "Small", min_pool_size=13)
    assert e_min.value.code is DatabaseErrorCode.INVALID_UNIVERSE_CONFIG

    # Invalid rarity rejected
    with pytest.raises(DatabaseError) as e_rar:
        db.add_character(
            character_id="bad_rar",
            universe_id="u1",
            name="Bad",
            canonical_version="v1",
            rarity="Mythic",  # not in 5-tier RARITY_TIERS
        )
    assert e_rar.value.code is DatabaseErrorCode.INVALID_RARITY

    # Incomplete candidate allowed in DRAFT, blocked from REVIEW
    db.add_character(
        character_id="cand_1",
        universe_id="u1",
        name="Candidate",
        canonical_version="v1",
        rarity="Common",
    )
    with pytest.raises(DatabaseError) as e_tr:
        db.submit_for_review("cand_1")
    assert e_tr.value.code is DatabaseErrorCode.INVALID_TRANSITION

    # Invalid float power rejected via Module 2
    with pytest.raises(DatabaseError) as e_flt:
        db.update_character_evaluation(
            "cand_1",
            power=3.0,  # type: ignore[arg-type]
            fit={r: 2 for r in SCORING_ROLES},
        )
    assert e_flt.value.code is DatabaseErrorCode.INVALID_CHARACTER

    # Populate 14 approved chars (below universe min_pool_size=15) -> blocked
    for i in range(14):
        cid = f"hero_{i}"
        db.add_character(
            character_id=cid,
            universe_id="u1",
            name=f"H{i}",
            canonical_version="v1",
            rarity="Common",
            power=3,
            fit={r: 2 for r in SCORING_ROLES},
            image=_verified_image(cid),
        )
        db.submit_for_review(cid)
        db.approve_character(cid)

    with pytest.raises(DatabaseError) as e_pub_min:
        db.publish_dataset("u1", "u1-v1")
    assert e_pub_min.value.code is DatabaseErrorCode.PUBLICATION_BLOCKED

    # Add 15th char with UNVERIFIED image -> still blocked for production
    db.update_character_evaluation(
        "cand_1",
        power=4,
        fit={r: 3 if r != "healer" else 0 for r in SCORING_ROLES},
    )
    db.submit_for_review("cand_1")
    db.approve_character("cand_1")
    with pytest.raises(DatabaseError) as e_img:
        db.publish_dataset("u1", "u1-v1")
    assert e_img.value.code is DatabaseErrorCode.PUBLICATION_BLOCKED

    # Verify image -> publishes cleanly even with zero healers (no mandatory healer quota)
    db.update_image_metadata("cand_1", _verified_image("cand_1"))
    manifest, report = db.publish_dataset("u1", "u1-v1")
    assert len(manifest.records) == 15
    assert report.healer_capable_count == 0
    assert report.advisory_only is True

    # Immutability: cannot republish same dataset_version
    with pytest.raises(DatabaseError) as e_dup_ver:
        db.publish_dataset("u1", "u1-v1")
    assert e_dup_ver.value.code is DatabaseErrorCode.VERSION_EXISTS

    # Deactivated universe blocks new production publication
    db.set_universe_active("u1", False)
    with pytest.raises(DatabaseError) as e_inact:
        db.publish_dataset("u1", "u1-v2")
    assert e_inact.value.code is DatabaseErrorCode.UNIVERSE_INACTIVE


def test_integration_with_modules_1_2_3_and_historical_pinning() -> None:
    db = CharacterDatabase()
    _populate_approved_universe(db, "uni_int", count=16, healer_fit=0)
    db.publish_dataset("uni_int", "uni_int-v1")

    # Module 1 exports catalog & weights directly from Module 4A
    catalog, weights, dver = db.export_draft_catalog("uni_int-v1")
    assert dver == "uni_int-v1"
    assert len(catalog) == 16
    assert set(weights.keys()) == set(RARITY_TIERS)

    src = SeededDrawSource(seed=42)
    snap = start_draft(
        match_id="m4a-001",
        players=("p1", "p2"),
        universe_id="uni_int",
        mode="ranked",
        catalog=catalog,
        rarity_weights=weights,
        dataset_version=dver,
        draw_source=src,
    ).snapshot
    completed = None
    while snap.active_player_id is not None:
        actor = snap.active_player_id
        snap = shuffle(snap, player_id=actor, expected_revision=snap.revision, draw_source=src).snapshot
        res = assign_role(snap, player_id=actor, role=snap.remaining_roles()[actor][0], expected_revision=snap.revision)
        snap = res.snapshot
        completed = res.completed_output

    assert completed is not None
    # Module 3 resolves directly against CharacterDatabase (DatasetReader)
    resolved_v1 = resolve_completed_draft(completed, db, player_order=("p1", "p2"))
    assert resolved_v1.ok is True
    assert resolved_v1.dataset_version == "uni_int-v1"

    # Reopen character, change ratings, re-approve, publish v2 -> v1 resolution unchanged
    db.reopen_to_draft("uni_int_char_00")
    db.update_character_evaluation("uni_int_char_00", power=5, fit={r: 5 for r in SCORING_ROLES})
    db.submit_for_review("uni_int_char_00")
    db.approve_character("uni_int_char_00")
    db.publish_dataset("uni_int", "uni_int-v2", predecessor_version="uni_int-v1")

    resolved_v1_again = resolve_completed_draft(completed, db, player_order=("p1", "p2"))
    assert resolved_v1_again.to_canonical_bytes() == resolved_v1.to_canonical_bytes()

    # Tamper stored hash in SQLite -> fail closed in both M4A and M3
    with db._conn:  # noqa: SLF001
        db._conn.execute(  # noqa: SLF001
            "UPDATE published_datasets SET content_hash = ? WHERE dataset_version = ?",
            ("0" * 64, "uni_int-v1"),
        )
    with pytest.raises(DatasetValidationError) as exc_hash:
        db.load_manifest("uni_int-v1")
    assert exc_hash.value.code is DatasetErrorCode.HASH_MISMATCH

    tampered_res = resolve_completed_draft(completed, db, player_order=("p1", "p2"))
    assert not tampered_res.ok
    assert tampered_res.error_code is ResolutionErrorCode.DATASET_INTEGRITY_FAILURE


def test_bulk_versioned_import_and_export() -> None:
    db = CharacterDatabase()
    db.create_universe("imp_u", "Import Universe")

    # 1. Catalogue import with incomplete candidate records
    catalogue_payload = {
        "format_version": IMPORT_FORMAT_VERSION,
        "batch_type": "catalogue",
        "universe_id": "imp_u",
        "characters": [
            {
                "character_id": "imp_01",
                "name": "Import Hero 1",
                "aliases": ["H1"],
                "species": "human",
                "canonical_version": "Base",
                "rarity": "Rare",
                "image": {"url_or_ref": "img/1.png", "status": "verified"},
            },
            {
                "character_id": "imp_02",
                "name": "Import Spirit 2",
                "species": "non_human",
                "canonical_version": "True Form",
                "rarity": "Epic",
            },
        ],
    }
    summary = import_catalogue_batch(db, json.dumps(catalogue_payload))
    assert summary.imported_count == 2
    assert db.get_character_entry("imp_01").status is EvaluationStatus.DRAFT
    assert db.get_character_entry("imp_02").power is None

    # 2. Evaluation batch import updates ratings & moves to REVIEW
    eval_payload = {
        "format_version": IMPORT_FORMAT_VERSION,
        "batch_type": "evaluation",
        "universe_id": "imp_u",
        "evaluations": [
            {
                "character_id": "imp_01",
                "power": 4,
                "fit": {r: 3 for r in SCORING_ROLES},
                "evidence": [{"target": "power", "grade": "A", "source_ref": "ch-5", "summary": "Feats"}],
                "source_references": ["ch-5"],
                "submit_for_review": True,
            }
        ],
    }
    eval_summary = import_evaluation_batch(db, eval_payload)
    assert eval_summary.imported_count == 1
    c1 = db.get_character_entry("imp_01")
    assert c1.status is EvaluationStatus.REVIEW
    assert c1.scores is not None and c1.scores["captain"] == 68  # 3*12 + 4*8

    # 3. Export bundle round-trip JSON
    exported = json.loads(export_universe_bundle(db, "imp_u"))
    assert exported["format_version"] == IMPORT_FORMAT_VERSION
    assert len(exported["characters"]) == 2
