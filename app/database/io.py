"""Versioned JSON import/export format (KA-IMPORT-1.0) for parallel development."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Mapping

from app.database.errors import DatabaseError, DatabaseErrorCode
from app.database.models import (
    EvaluationStatus,
    EvidenceItem,
    ImageMetadata,
    ImageValidationStatus,
    RARITY_SET,
    SpeciesKind,
)
from app.database.repository import CharacterDatabase
from app.scoring import SCORE_1_0_CONFIG, ScoringConfig

IMPORT_FORMAT_VERSION = "KA-IMPORT-1.0"


@dataclass(frozen=True, slots=True)
class ImportSummary:
    format_version: str
    kind: str
    universe_id: str
    imported_count: int
    character_ids: tuple[str, ...]


def _parse_json_payload(payload: Mapping[str, Any] | str) -> Mapping[str, Any]:
    if isinstance(payload, str):
        try:
            data = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise DatabaseError(
                DatabaseErrorCode.INVALID_IMPORT_FORMAT,
                f"Invalid JSON payload: {exc}",
            ) from exc
    elif isinstance(payload, Mapping):
        data = payload
    else:
        raise DatabaseError(
            DatabaseErrorCode.INVALID_IMPORT_FORMAT,
            "Import payload must be a JSON string or mapping",
        )
    if data.get("format_version") != IMPORT_FORMAT_VERSION:
        raise DatabaseError(
            DatabaseErrorCode.INVALID_IMPORT_FORMAT,
            f"Unsupported format_version {data.get('format_version')!r}; expected {IMPORT_FORMAT_VERSION!r}",
        )
    return data


def import_catalogue_batch(
    db: CharacterDatabase,
    payload: Mapping[str, Any] | str,
    *,
    config: ScoringConfig = SCORE_1_0_CONFIG,
) -> ImportSummary:
    """Import a character catalogue batch (supports incomplete candidate records).

    Incomplete records (missing power/fit) are stored in ``draft`` status and never
    treated as approved playable characters.
    """
    data = _parse_json_payload(payload)
    if data.get("batch_type") != "catalogue":
        raise DatabaseError(
            DatabaseErrorCode.INVALID_IMPORT_FORMAT,
            "Expected batch_type='catalogue'",
        )
    universe_id = data.get("universe_id")
    if not isinstance(universe_id, str) or not universe_id.strip():
        raise DatabaseError(
            DatabaseErrorCode.INVALID_IMPORT_FORMAT,
            "universe_id must be a non-empty string",
        )
    db.get_universe(universe_id)

    records = data.get("characters")
    if not isinstance(records, list) or not records:
        raise DatabaseError(
            DatabaseErrorCode.INVALID_IMPORT_FORMAT,
            "characters must be a non-empty list",
        )

    # Pre-validate uniqueness within batch
    seen: set[str] = set()
    for item in records:
        if not isinstance(item, Mapping):
            raise DatabaseError(
                DatabaseErrorCode.INVALID_IMPORT_FORMAT,
                "Each character entry must be an object",
            )
        cid = item.get("character_id")
        if not isinstance(cid, str) or not cid.strip():
            raise DatabaseError(
                DatabaseErrorCode.INVALID_IMPORT_FORMAT,
                "Each character requires a non-empty character_id",
            )
        if cid in seen:
            raise DatabaseError(
                DatabaseErrorCode.INVALID_IMPORT_FORMAT,
                f"Duplicate character_id {cid!r} in import batch",
            )
        seen.add(cid)
        rarity = item.get("rarity")
        if rarity not in RARITY_SET:
            raise DatabaseError(
                DatabaseErrorCode.INVALID_RARITY,
                f"Invalid rarity {rarity!r} for {cid!r}",
            )

    imported: list[str] = []
    with db._conn:  # atomic transaction across entire batch
        pass
    # Execute inside a single rollback-safe SQLite transaction
    try:
        db._conn.execute("BEGIN")
        for item in records:
            img_raw = item.get("image") or {}
            img = ImageMetadata(
                url_or_ref=str(img_raw.get("url_or_ref", "")),
                source_ref=str(img_raw.get("source_ref", "")),
                mime_type=str(img_raw.get("mime_type", "")),
                width=img_raw.get("width"),
                height=img_raw.get("height"),
                checksum=str(img_raw.get("checksum", "")),
                status=ImageValidationStatus(
                    img_raw.get("status", ImageValidationStatus.PENDING.value)
                ),
            )
            ev = tuple(
                EvidenceItem.from_dict(e) for e in (item.get("evidence") or ())
            )
            entry = db.add_character(
                character_id=item["character_id"],
                universe_id=universe_id,
                name=item["name"],
                aliases=tuple(item.get("aliases") or ()),
                species=SpeciesKind(item.get("species", SpeciesKind.HUMAN.value)),
                canonical_version=item["canonical_version"],
                rarity=item["rarity"],
                power=item.get("power"),
                fit=item.get("fit"),
                evidence=ev,
                source_references=tuple(item.get("source_references") or ()),
                image=img,
                status=EvaluationStatus.DRAFT,  # candidates always enter as draft
                revision_ref=str(item.get("revision_ref", "import-1")),
                config=config,
            )
            imported.append(entry.character_id)
        db._conn.commit()
    except Exception:
        db._conn.rollback()
        raise

    return ImportSummary(
        format_version=IMPORT_FORMAT_VERSION,
        kind="catalogue",
        universe_id=universe_id,
        imported_count=len(imported),
        character_ids=tuple(imported),
    )


def import_evaluation_batch(
    db: CharacterDatabase,
    payload: Mapping[str, Any] | str,
    *,
    config: ScoringConfig = SCORE_1_0_CONFIG,
) -> ImportSummary:
    """Import an AI evaluation batch updating ratings/evidence and optional review status."""
    data = _parse_json_payload(payload)
    if data.get("batch_type") != "evaluation":
        raise DatabaseError(
            DatabaseErrorCode.INVALID_IMPORT_FORMAT,
            "Expected batch_type='evaluation'",
        )
    universe_id = data.get("universe_id")
    if not isinstance(universe_id, str) or not universe_id.strip():
        raise DatabaseError(
            DatabaseErrorCode.INVALID_IMPORT_FORMAT,
            "universe_id must be a non-empty string",
        )
    db.get_universe(universe_id)

    evaluations = data.get("evaluations")
    if not isinstance(evaluations, list) or not evaluations:
        raise DatabaseError(
            DatabaseErrorCode.INVALID_IMPORT_FORMAT,
            "evaluations must be a non-empty list",
        )

    updated: list[str] = []
    for item in evaluations:
        if not isinstance(item, Mapping):
            raise DatabaseError(
                DatabaseErrorCode.INVALID_IMPORT_FORMAT,
                "Each evaluation item must be an object",
            )
        cid = item.get("character_id")
        if not isinstance(cid, str) or not cid.strip():
            raise DatabaseError(
                DatabaseErrorCode.INVALID_IMPORT_FORMAT,
                "Evaluation requires character_id",
            )
        existing = db.get_character_entry(cid)
        if existing.universe_id != universe_id:
            raise DatabaseError(
                DatabaseErrorCode.INVALID_IMPORT_FORMAT,
                f"Character {cid!r} does not belong to universe {universe_id!r}",
            )
        ev = tuple(EvidenceItem.from_dict(e) for e in (item.get("evidence") or ()))
        refs = tuple(str(r) for r in (item.get("source_references") or ()))
        db.update_character_evaluation(
            cid,
            power=item.get("power"),  # type: ignore[arg-type]
            fit=item.get("fit"),  # type: ignore[arg-type]
            evidence=ev,
            source_references=refs,
            revision_ref=str(item.get("revision_ref", existing.revision_ref)),
            config=config,
        )
        if item.get("submit_for_review"):
            db.submit_for_review(cid, config=config)
        updated.append(cid)

    return ImportSummary(
        format_version=IMPORT_FORMAT_VERSION,
        kind="evaluation",
        universe_id=universe_id,
        imported_count=len(updated),
        character_ids=tuple(updated),
    )


def export_universe_bundle(db: CharacterDatabase, universe_id: str) -> str:
    """Export universe metadata and all character records as deterministic JSON."""
    universe = db.get_universe(universe_id)
    characters = db.list_characters(universe_id)
    payload = {
        "format_version": IMPORT_FORMAT_VERSION,
        "universe": universe.to_dict(),
        "characters": [c.to_dict() for c in characters],
    }
    return json.dumps(payload, sort_keys=True, indent=2, ensure_ascii=False)


def export_published_dataset(db: CharacterDatabase, dataset_version: str) -> str:
    """Export a verified published dataset manifest + health report as JSON."""
    manifest = db.load_manifest(dataset_version)
    health = db.get_health_report(dataset_version)
    payload = {
        "format_version": IMPORT_FORMAT_VERSION,
        "dataset_version": manifest.dataset_version,
        "kind": manifest.kind.value,
        "scoring_version": manifest.scoring_version,
        "content_hash": manifest.content_hash,
        "governing_versions": manifest.governing_versions.to_dict(),
        "created_at": manifest.created_at,
        "predecessor_version": manifest.predecessor_version,
        "records": [r.to_canonical_dict() for r in manifest.records],
        "health_report": health,
    }
    return json.dumps(payload, sort_keys=True, indent=2, ensure_ascii=False)
