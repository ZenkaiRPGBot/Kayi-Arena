"""Dataset version manifests, integrity checks, and in-memory adapter (DV1-DV8)."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType
from typing import Any, Mapping, Sequence

from app.scoring.engine import score_batch
from app.scoring.errors import DatasetErrorCode, DatasetValidationError
from app.scoring.models import SCORING_ROLES, ScoringConfig


class DatasetKind(str, Enum):
    PRODUCTION = "production"
    SANDBOX = "sandbox"
    TEST = "test"


class RecordStatus(str, Enum):
    APPROVED = "approved"
    DRAFT = "draft"


@dataclass(frozen=True, slots=True)
class GoverningVersions:
    universe_policy_version: str
    anchor_set_version: str
    calibration_set_version: str

    def to_dict(self) -> dict[str, str]:
        return {
            "universe_policy_version": self.universe_policy_version,
            "anchor_set_version": self.anchor_set_version,
            "calibration_set_version": self.calibration_set_version,
        }


@dataclass(frozen=True, slots=True)
class DatasetRecord:
    """Published character rating + precomputed scores within a dataset version."""

    character_id: str
    power: int
    fit: Mapping[str, int]
    scores: Mapping[str, int]
    status: RecordStatus
    revision_ref: str
    scoring_version: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "fit", MappingProxyType(dict(self.fit)))
        object.__setattr__(self, "scores", MappingProxyType(dict(self.scores)))

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "character_id": self.character_id,
            "power": self.power,
            "fit": {role: self.fit[role] for role in SCORING_ROLES},
            "scores": {role: self.scores[role] for role in SCORING_ROLES},
            "status": self.status.value,
            "revision_ref": self.revision_ref,
            "scoring_version": self.scoring_version,
        }


@dataclass(frozen=True, slots=True)
class DatasetManifest:
    """Logical dataset version manifest (Module 2 Section 4)."""

    dataset_version: str
    kind: DatasetKind
    scoring_version: str
    records: tuple[DatasetRecord, ...]
    governing_versions: GoverningVersions
    content_hash: str
    created_at: str
    predecessor_version: str | None = None

    def canonical_payload(self) -> str:
        payload = {
            "dataset_version": self.dataset_version,
            "kind": self.kind.value,
            "scoring_version": self.scoring_version,
            "records": [r.to_canonical_dict() for r in sorted(self.records, key=lambda x: x.character_id)],
            "governing_versions": self.governing_versions.to_dict(),
            "created_at": self.created_at,
            "predecessor_version": self.predecessor_version,
        }
        return json.dumps(payload, sort_keys=True, separators=(",", ":"))

    def compute_content_hash(self) -> str:
        return hashlib.sha256(self.canonical_payload().encode("utf-8")).hexdigest()


def build_signed_manifest(
    *,
    dataset_version: str,
    kind: DatasetKind,
    config: ScoringConfig,
    records: Sequence[DatasetRecord],
    governing_versions: GoverningVersions,
    created_at: str,
    predecessor_version: str | None = None,
) -> DatasetManifest:
    """Construct a manifest with its canonical SHA-256 content hash."""
    draft_manifest = DatasetManifest(
        dataset_version=dataset_version,
        kind=kind,
        scoring_version=config.version,
        records=tuple(records),
        governing_versions=governing_versions,
        content_hash="",
        created_at=created_at,
        predecessor_version=predecessor_version,
    )
    return DatasetManifest(
        dataset_version=draft_manifest.dataset_version,
        kind=draft_manifest.kind,
        scoring_version=draft_manifest.scoring_version,
        records=draft_manifest.records,
        governing_versions=draft_manifest.governing_versions,
        content_hash=draft_manifest.compute_content_hash(),
        created_at=draft_manifest.created_at,
        predecessor_version=draft_manifest.predecessor_version,
    )


def validate_manifest_for_publication(
    manifest: DatasetManifest,
    *,
    config: ScoringConfig,
) -> None:
    """Enforce DV1, DV3, DV4, DV7, DV8 before publishing a dataset version."""
    if not manifest.dataset_version.strip():
        raise DatasetValidationError(
            DatasetErrorCode.INVALID_MANIFEST, "dataset_version must be non-empty"
        )
    if manifest.scoring_version != config.version:
        raise DatasetValidationError(
            DatasetErrorCode.MIXED_SCORING_VERSION,
            f"Manifest scoring_version {manifest.scoring_version!r} does not match {config.version!r}",
        )

    # DV3: Content hash verification
    if manifest.content_hash != manifest.compute_content_hash():
        raise DatasetValidationError(
            DatasetErrorCode.HASH_MISMATCH,
            "Manifest content_hash does not match canonical payload",
        )

    # DV7 & DV1 & DV8 per-record checks
    seen_ids: set[str] = set()
    raw_inputs = []
    for rec in manifest.records:
        if rec.character_id in seen_ids:
            raise DatasetValidationError(
                DatasetErrorCode.DUPLICATE_CHARACTER,
                f"Duplicate character_id {rec.character_id!r} in dataset {manifest.dataset_version!r}",
            )
        seen_ids.add(rec.character_id)

        if rec.scoring_version != manifest.scoring_version:
            raise DatasetValidationError(
                DatasetErrorCode.MIXED_SCORING_VERSION,
                f"Record {rec.character_id!r} has scoring_version {rec.scoring_version!r}, expected {manifest.scoring_version!r}",
            )

        if manifest.kind is DatasetKind.PRODUCTION and rec.status is not RecordStatus.APPROVED:
            raise DatasetValidationError(
                DatasetErrorCode.NON_APPROVED_IN_PRODUCTION,
                f"Production dataset cannot contain {rec.status.value} record {rec.character_id!r}",
            )

        raw_inputs.append(
            {"character_id": rec.character_id, "power": rec.power, "fit": dict(rec.fit)}
        )

    # DV4: Recompute all role scores and verify exact match
    batch = score_batch(raw_inputs, config=config)
    if not batch.accepted:
        raise DatasetValidationError(
            DatasetErrorCode.INVALID_MANIFEST,
            f"Batch rating validation failed: {batch.errors}",
        )

    expected_by_id = {out.character_id: out for out in batch.results}
    for rec in manifest.records:
        recomputed = expected_by_id[rec.character_id]
        if dict(rec.scores) != dict(recomputed.scores):
            raise DatasetValidationError(
                DatasetErrorCode.SCORE_MISMATCH,
                f"Stored scores for {rec.character_id!r} do not match recomputation",
            )


class InMemoryDatasetRepository:
    """Lightweight test adapter for dataset publication and version-pinned retrieval."""

    def __init__(self) -> None:
        self._versions: dict[str, DatasetManifest] = {}

    def publish(self, manifest: DatasetManifest, *, config: ScoringConfig) -> DatasetManifest:
        # DV2: published version is immutable
        if manifest.dataset_version in self._versions:
            raise DatasetValidationError(
                DatasetErrorCode.VERSION_IMMUTABLE,
                f"Dataset version {manifest.dataset_version!r} is already published",
            )
        validate_manifest_for_publication(manifest, config=config)
        self._versions[manifest.dataset_version] = manifest
        return manifest

    def load_version(self, dataset_version: str) -> DatasetManifest:
        manifest = self._versions.get(dataset_version)
        if manifest is None:
            raise DatasetValidationError(
                DatasetErrorCode.VERSION_NOT_FOUND,
                f"Dataset version {dataset_version!r} not found",
            )
        # DV3: verify hash on every load; fail closed
        if manifest.content_hash != manifest.compute_content_hash():
            raise DatasetValidationError(
                DatasetErrorCode.HASH_MISMATCH,
                f"Hash mismatch on load for dataset {dataset_version!r}",
            )
        return manifest

    def get_character_for_resolution(
        self, dataset_version: str, character_id: str
    ) -> DatasetRecord:
        """Module 3 read boundary: fetch ratings/scores from the match's pinned version."""
        manifest = self.load_version(dataset_version)
        for rec in manifest.records:
            if rec.character_id == character_id:
                return rec
        raise KeyError(
            f"Character {character_id!r} not found in dataset version {dataset_version!r}"
        )
