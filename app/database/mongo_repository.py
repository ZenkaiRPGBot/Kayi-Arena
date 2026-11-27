"""MongoDB Atlas-backed CharacterDatabase & DatasetPublisher (Modules 1-4A compatible)."""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Mapping, Sequence

from app.database.errors import DatabaseError, DatabaseErrorCode
from app.database.health import DatasetHealthReport, build_dataset_health_report
from app.database.models import (
    CharacterEntry,
    DEFAULT_RARITY_WEIGHTS,
    EvaluationStatus,
    EvidenceItem,
    ImageMetadata,
    ImageValidationStatus,
    RARITY_SET,
    RARITY_TIERS,
    SpeciesKind,
    Universe,
)
from app.database.repository import (
    _manifest_from_json,
    _manifest_to_json,
    _utc_now,
    _validate_rarity_weights,
)
from app.engine import CatalogEntry, MIN_POOL_SIZE
from app.scoring import (
    BatchValidationError,
    DatasetErrorCode,
    DatasetKind,
    DatasetManifest,
    DatasetRecord,
    DatasetValidationError,
    GoverningVersions,
    RecordStatus,
    SCORE_1_0_CONFIG,
    SCORING_ROLES,
    ScoringConfig,
    build_signed_manifest,
    score_record,
    validate_manifest_for_publication,
)

logger = logging.getLogger(__name__)


class MongoCharacterDatabase:
    """MongoDB Atlas character database & immutable dataset publisher."""

    def __init__(
        self,
        uri: str = "",
        *,
        database_name: str = "kayi_arena",
        client: Any = None,
        database: Any = None,
    ) -> None:
        self._owns_client = False
        self._manifest_cache: dict[str, DatasetManifest] = {}
        self._dataset_record_cache: dict[str, dict[str, DatasetRecord]] = {}
        if database is not None:
            self._client = client
            self._db = database
        else:
            try:
                from pymongo import MongoClient
            except ImportError as exc:
                raise RuntimeError(
                    "pymongo is required when DB_BACKEND=mongodb. Install pymongo>=4.6."
                ) from exc
            if client is None and not uri:
                raise ValueError("MONGODB_URI is required when DB_BACKEND=mongodb.")
            self._client = client or MongoClient(
                uri,
                serverSelectionTimeoutMS=5000,
                connectTimeoutMS=5000,
                socketTimeoutMS=10000,
            )
            self._owns_client = client is None
            self._db = self._client[database_name]
        self._ensure_indexes()

    def _ensure_indexes(self) -> None:
        try:
            self._db.command("ping")
            self._db["characters"].create_index([("universe_id", 1), ("status", 1)])
            self._db["characters"].create_index([("universe_id", 1), ("name", 1)])
            self._db["published_datasets"].create_index([("universe_id", 1), ("kind", 1)])
        except Exception as exc:
            logger.debug("MongoCharacterDatabase index check skipped: %s", exc)

    def __enter__(self) -> MongoCharacterDatabase:
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def close(self) -> None:
        if self._owns_client and self._client is not None:
            self._client.close()

    # ------------------------------------------------------------------
    # Universe management
    # ------------------------------------------------------------------

    def create_universe(
        self,
        universe_id: str,
        name: str,
        *,
        active: bool = True,
        rarity_weights: Mapping[str, float] | None = None,
        min_pool_size: int = MIN_POOL_SIZE,
        policy_version: str = "UP-1.0",
        now: str | None = None,
    ) -> Universe:
        uid = universe_id.strip() if isinstance(universe_id, str) else ""
        uname = name.strip() if isinstance(name, str) else ""
        if not uid or not uname:
            raise DatabaseError(
                DatabaseErrorCode.INVALID_UNIVERSE_CONFIG,
                "universe_id and name must be non-empty strings",
            )
        if type(min_pool_size) is not int or min_pool_size < MIN_POOL_SIZE:
            raise DatabaseError(
                DatabaseErrorCode.INVALID_UNIVERSE_CONFIG,
                f"min_pool_size must be an integer >= {MIN_POOL_SIZE}",
            )
        weights = _validate_rarity_weights(rarity_weights or DEFAULT_RARITY_WEIGHTS)
        ts = now or _utc_now()
        if self._db["universes"].find_one({"_id": uid}) is not None:
            raise DatabaseError(
                DatabaseErrorCode.UNIVERSE_EXISTS,
                f"Universe {uid!r} already exists",
            )
        self._db["universes"].replace_one(
            {"_id": uid},
            {
                "_id": uid,
                "universe_id": uid,
                "name": uname,
                "active": bool(active),
                "rarity_weights": dict(weights),
                "min_pool_size": int(min_pool_size),
                "policy_version": policy_version,
                "created_at": ts,
                "updated_at": ts,
            },
            upsert=True,
        )
        return self.get_universe(uid)

    def _doc_to_universe(self, doc: dict[str, Any]) -> Universe:
        return Universe(
            universe_id=str(doc["universe_id"]),
            name=str(doc["name"]),
            active=bool(doc["active"]),
            rarity_weights=dict(doc["rarity_weights"]),
            min_pool_size=int(doc["min_pool_size"]),
            policy_version=str(doc["policy_version"]),
            created_at=str(doc["created_at"]),
            updated_at=str(doc["updated_at"]),
        )

    def get_universe(self, universe_id: str) -> Universe:
        doc = self._db["universes"].find_one({"_id": universe_id})
        if doc is None:
            raise DatabaseError(
                DatabaseErrorCode.UNIVERSE_NOT_FOUND,
                f"Universe {universe_id!r} not found",
            )
        return self._doc_to_universe(doc)

    def list_universes(self, *, active_only: bool = False) -> tuple[Universe, ...]:
        query = {"active": True} if active_only else {}
        docs = list(self._db["universes"].find(query))
        docs.sort(key=lambda d: str(d.get("universe_id", "")))
        return tuple(self._doc_to_universe(d) for d in docs)

    def set_universe_active(
        self, universe_id: str, active: bool, *, now: str | None = None
    ) -> Universe:
        self.get_universe(universe_id)
        ts = now or _utc_now()
        self._db["universes"].update_one(
            {"_id": universe_id},
            {"$set": {"active": bool(active), "updated_at": ts}},
        )
        return self.get_universe(universe_id)

    def update_universe_weights(
        self,
        universe_id: str,
        rarity_weights: Mapping[str, float],
        *,
        now: str | None = None,
    ) -> Universe:
        self.get_universe(universe_id)
        weights = _validate_rarity_weights(rarity_weights)
        ts = now or _utc_now()
        self._db["universes"].update_one(
            {"_id": universe_id},
            {"$set": {"rarity_weights": dict(weights), "updated_at": ts}},
        )
        return self.get_universe(universe_id)

    # ------------------------------------------------------------------
    # Character catalogue & evaluation lifecycle
    # ------------------------------------------------------------------

    def _validate_and_score_ratings(
        self,
        character_id: str,
        power: int | None,
        fit: Mapping[str, int] | None,
        config: ScoringConfig,
    ) -> tuple[int | None, dict[str, int] | None, dict[str, int] | None, str | None]:
        if power is None and fit is None:
            return None, None, None, None
        if power is None or fit is None:
            raise DatabaseError(
                DatabaseErrorCode.INVALID_CHARACTER,
                "power and fit must both be provided or both omitted for incomplete drafts",
            )
        try:
            scored = score_record(
                {"character_id": character_id, "power": power, "fit": dict(fit)},
                config=config,
            )
        except BatchValidationError as exc:
            raise DatabaseError(
                DatabaseErrorCode.INVALID_CHARACTER,
                f"Module 2 rating validation failed: {exc}",
            ) from exc
        return (
            int(power),
            {r: int(fit[r]) for r in SCORING_ROLES},
            dict(scored.scores),
            scored.scoring_version,
        )

    def _doc_to_character(self, doc: dict[str, Any]) -> CharacterEntry:
        return CharacterEntry(
            character_id=str(doc["character_id"]),
            universe_id=str(doc["universe_id"]),
            name=str(doc["name"]),
            aliases=tuple(doc.get("aliases") or ()),
            species=SpeciesKind(str(doc["species"])),
            canonical_version=str(doc["canonical_version"]),
            rarity=str(doc["rarity"]),
            power=doc.get("power"),
            fit=doc.get("fit"),
            scores=doc.get("scores"),
            scoring_version=doc.get("scoring_version"),
            evidence=tuple(EvidenceItem.from_dict(e) for e in (doc.get("evidence") or ())),
            source_references=tuple(doc.get("source_references") or ()),
            image=ImageMetadata.from_dict(doc.get("image") or {}),
            status=EvaluationStatus(str(doc["status"])),
            revision_ref=str(doc.get("revision_ref", "rev-1")),
            created_at=str(doc["created_at"]),
            updated_at=str(doc["updated_at"]),
        )

    def add_character(
        self,
        *,
        character_id: str,
        universe_id: str,
        name: str,
        canonical_version: str,
        rarity: str,
        aliases: Sequence[str] = (),
        species: SpeciesKind | str = SpeciesKind.HUMAN,
        power: int | None = None,
        fit: Mapping[str, int] | None = None,
        evidence: Sequence[EvidenceItem] = (),
        source_references: Sequence[str] = (),
        image: ImageMetadata | None = None,
        status: EvaluationStatus | str = EvaluationStatus.DRAFT,
        revision_ref: str = "rev-1",
        config: ScoringConfig = SCORE_1_0_CONFIG,
        now: str | None = None,
    ) -> CharacterEntry:
        cid = character_id.strip() if isinstance(character_id, str) else ""
        cname = name.strip() if isinstance(name, str) else ""
        cver = canonical_version.strip() if isinstance(canonical_version, str) else ""
        if not cid or not cname or not cver:
            raise DatabaseError(
                DatabaseErrorCode.INVALID_CHARACTER,
                "character_id, name, and canonical_version must be non-empty",
            )
        self.get_universe(universe_id)
        if rarity not in RARITY_SET:
            raise DatabaseError(
                DatabaseErrorCode.INVALID_RARITY,
                f"Invalid rarity {rarity!r}; must be one of {RARITY_TIERS}",
            )
        sp = species if isinstance(species, SpeciesKind) else SpeciesKind(str(species))
        st = status if isinstance(status, EvaluationStatus) else EvaluationStatus(str(status))

        p_val, f_val, s_val, s_ver = self._validate_and_score_ratings(cid, power, fit, config)
        if st is not EvaluationStatus.DRAFT and (p_val is None or f_val is None):
            raise DatabaseError(
                DatabaseErrorCode.INVALID_TRANSITION,
                "Cannot create non-draft character without valid power and fit ratings",
            )

        if self._db["characters"].find_one({"_id": cid}) is not None:
            raise DatabaseError(
                DatabaseErrorCode.DUPLICATE_CHARACTER,
                f"Character {cid!r} already exists",
            )
        existing_names = self._db["characters"].find({"universe_id": universe_id})
        for d in existing_names:
            if str(d.get("name", "")).lower() == cname.lower():
                raise DatabaseError(
                    DatabaseErrorCode.DUPLICATE_CHARACTER,
                    f"Character name {cname!r} already exists in universe {universe_id!r}",
                )

        ts = now or _utc_now()
        img = image or ImageMetadata()
        self._db["characters"].replace_one(
            {"_id": cid},
            {
                "_id": cid,
                "character_id": cid,
                "universe_id": universe_id,
                "name": cname,
                "aliases": [str(a) for a in aliases],
                "species": sp.value,
                "canonical_version": cver,
                "rarity": rarity,
                "power": p_val,
                "fit": f_val,
                "scores": s_val,
                "scoring_version": s_ver,
                "evidence": [e.to_dict() for e in evidence],
                "source_references": [str(s) for s in source_references],
                "image": img.to_dict(),
                "status": st.value,
                "revision_ref": revision_ref,
                "created_at": ts,
                "updated_at": ts,
            },
            upsert=True,
        )
        return self.get_character_entry(cid)

    def get_character_entry(self, character_id: str) -> CharacterEntry:
        doc = self._db["characters"].find_one({"_id": character_id})
        if doc is None:
            raise DatabaseError(
                DatabaseErrorCode.CHARACTER_NOT_FOUND,
                f"Character {character_id!r} not found",
            )
        return self._doc_to_character(doc)

    def list_characters(
        self,
        universe_id: str,
        *,
        status: EvaluationStatus | None = None,
    ) -> tuple[CharacterEntry, ...]:
        query: dict[str, Any] = {"universe_id": universe_id}
        if status is not None:
            query["status"] = status.value
        docs = list(self._db["characters"].find(query))
        docs.sort(key=lambda d: str(d.get("character_id", "")))
        return tuple(self._doc_to_character(d) for d in docs)

    def update_character_evaluation(
        self,
        character_id: str,
        *,
        power: int | None = None,
        fit: Mapping[str, int] | None = None,
        rarity: str | None = None,
        evidence: Sequence[EvidenceItem] | None = None,
        source_references: Sequence[str] | None = None,
        revision_ref: str | None = None,
        config: ScoringConfig = SCORE_1_0_CONFIG,
        now: str | None = None,
    ) -> CharacterEntry:
        entry = self.get_character_entry(character_id)
        if entry.status is not EvaluationStatus.DRAFT:
            raise DatabaseError(
                DatabaseErrorCode.INVALID_TRANSITION,
                f"Character {character_id!r} must be reopened to 'draft' before editing (currently {entry.status.value})",
            )
        new_rarity = rarity if rarity is not None else entry.rarity
        if new_rarity not in RARITY_SET:
            raise DatabaseError(
                DatabaseErrorCode.INVALID_RARITY,
                f"Invalid rarity {new_rarity!r}",
            )
        p_in = power if power is not None else entry.power
        f_in = fit if fit is not None else entry.fit
        p_val, f_val, s_val, s_ver = self._validate_and_score_ratings(
            character_id, p_in, f_in, config
        )
        ev_val = [e.to_dict() for e in (evidence if evidence is not None else entry.evidence)]
        sr_val = [str(s) for s in (source_references if source_references is not None else entry.source_references)]
        rev = revision_ref or entry.revision_ref
        ts = now or _utc_now()
        self._db["characters"].update_one(
            {"_id": character_id},
            {
                "$set": {
                    "rarity": new_rarity,
                    "power": p_val,
                    "fit": f_val,
                    "scores": s_val,
                    "scoring_version": s_ver,
                    "evidence": ev_val,
                    "source_references": sr_val,
                    "revision_ref": rev,
                    "updated_at": ts,
                }
            },
        )
        return self.get_character_entry(character_id)

    def update_image_metadata(
        self,
        character_id: str,
        image: ImageMetadata,
        *,
        now: str | None = None,
    ) -> CharacterEntry:
        self.get_character_entry(character_id)
        ts = now or _utc_now()
        self._db["characters"].update_one(
            {"_id": character_id},
            {"$set": {"image": image.to_dict(), "updated_at": ts}},
        )
        return self.get_character_entry(character_id)

    def submit_for_review(
        self,
        character_id: str,
        *,
        config: ScoringConfig = SCORE_1_0_CONFIG,
        now: str | None = None,
    ) -> CharacterEntry:
        entry = self.get_character_entry(character_id)
        if entry.status is not EvaluationStatus.DRAFT:
            raise DatabaseError(
                DatabaseErrorCode.INVALID_TRANSITION,
                f"submit_for_review requires 'draft' status (got {entry.status.value})",
            )
        if entry.power is None or entry.fit is None:
            raise DatabaseError(
                DatabaseErrorCode.INVALID_TRANSITION,
                f"Cannot submit incomplete draft {character_id!r} without power and fit",
            )
        _, _, s_val, s_ver = self._validate_and_score_ratings(
            character_id, entry.power, entry.fit, config
        )
        ts = now or _utc_now()
        self._db["characters"].update_one(
            {"_id": character_id},
            {
                "$set": {
                    "status": EvaluationStatus.REVIEW.value,
                    "scores": s_val,
                    "scoring_version": s_ver,
                    "updated_at": ts,
                }
            },
        )
        return self.get_character_entry(character_id)

    def approve_character(
        self, character_id: str, *, now: str | None = None
    ) -> CharacterEntry:
        entry = self.get_character_entry(character_id)
        if entry.status is not EvaluationStatus.REVIEW:
            raise DatabaseError(
                DatabaseErrorCode.INVALID_TRANSITION,
                f"approve_character requires 'review' status (got {entry.status.value})",
            )
        if entry.power is None or entry.fit is None or entry.scores is None:
            raise DatabaseError(
                DatabaseErrorCode.INVALID_TRANSITION,
                f"Cannot approve character {character_id!r} without complete scores",
            )
        ts = now or _utc_now()
        self._db["characters"].update_one(
            {"_id": character_id},
            {"$set": {"status": EvaluationStatus.APPROVED.value, "updated_at": ts}},
        )
        return self.get_character_entry(character_id)

    def reopen_to_draft(
        self, character_id: str, *, now: str | None = None
    ) -> CharacterEntry:
        entry = self.get_character_entry(character_id)
        if entry.status is EvaluationStatus.DRAFT:
            return entry
        ts = now or _utc_now()
        self._db["characters"].update_one(
            {"_id": character_id},
            {"$set": {"status": EvaluationStatus.DRAFT.value, "updated_at": ts}},
        )
        return self.get_character_entry(character_id)

    # ------------------------------------------------------------------
    # Dataset Publication & Module 3 DatasetReader Contract
    # ------------------------------------------------------------------

    def publish_dataset(
        self,
        universe_id: str,
        dataset_version: str,
        *,
        kind: DatasetKind = DatasetKind.PRODUCTION,
        character_ids: Sequence[str] | None = None,
        anchor_set_version: str = "ANCHOR-1.0",
        calibration_set_version: str = "CAL-1.0",
        predecessor_version: str | None = None,
        config: ScoringConfig = SCORE_1_0_CONFIG,
        now: str | None = None,
    ) -> tuple[DatasetManifest, DatasetHealthReport]:
        universe = self.get_universe(universe_id)
        dver = dataset_version.strip() if isinstance(dataset_version, str) else ""
        if not dver:
            raise DatabaseError(
                DatabaseErrorCode.PUBLICATION_BLOCKED,
                "dataset_version must be non-empty",
            )
        if self._db["published_datasets"].find_one({"_id": dver}) is not None:
            raise DatabaseError(
                DatabaseErrorCode.VERSION_EXISTS,
                f"Dataset version {dver!r} already exists (immutable)",
            )
        if kind is DatasetKind.PRODUCTION and not universe.active:
            raise DatabaseError(
                DatabaseErrorCode.UNIVERSE_INACTIVE,
                f"Cannot publish production dataset for inactive universe {universe_id!r}",
            )

        if character_ids is not None:
            if len(set(character_ids)) != len(character_ids):
                raise DatabaseError(
                    DatabaseErrorCode.PUBLICATION_BLOCKED,
                    "Duplicate character_id in publication selection",
                )
            entries = tuple(self.get_character_entry(cid) for cid in character_ids)
            for e in entries:
                if e.universe_id != universe_id:
                    raise DatabaseError(
                        DatabaseErrorCode.PUBLICATION_BLOCKED,
                        f"Character {e.character_id!r} belongs to {e.universe_id!r}, not {universe_id!r}",
                    )
        else:
            if kind is DatasetKind.PRODUCTION:
                entries = self.list_characters(universe_id, status=EvaluationStatus.APPROVED)
            else:
                entries = tuple(
                    c
                    for c in self.list_characters(universe_id)
                    if c.power is not None and c.fit is not None
                )

        min_required = max(MIN_POOL_SIZE, universe.min_pool_size)
        if len(entries) < min_required:
            raise DatabaseError(
                DatabaseErrorCode.PUBLICATION_BLOCKED,
                f"Need at least {min_required} eligible characters to publish (got {len(entries)})",
            )

        ds_records: list[DatasetRecord] = []
        scored_outputs = []
        for entry in entries:
            if entry.rarity not in RARITY_SET:
                raise DatabaseError(
                    DatabaseErrorCode.INVALID_RARITY,
                    f"Character {entry.character_id!r} has invalid rarity {entry.rarity!r}",
                )
            if kind is DatasetKind.PRODUCTION:
                if entry.status is not EvaluationStatus.APPROVED:
                    raise DatabaseError(
                        DatabaseErrorCode.PUBLICATION_BLOCKED,
                        f"Production publication blocked: {entry.character_id!r} is {entry.status.value}",
                    )
                if entry.image.status is not ImageValidationStatus.VERIFIED:
                    raise DatabaseError(
                        DatabaseErrorCode.PUBLICATION_BLOCKED,
                        f"Production publication blocked: {entry.character_id!r} image is {entry.image.status.value}",
                    )

            if entry.power is None or entry.fit is None:
                raise DatabaseError(
                    DatabaseErrorCode.PUBLICATION_BLOCKED,
                    f"Character {entry.character_id!r} has incomplete ratings",
                )

            scored = score_record(
                {"character_id": entry.character_id, "power": entry.power, "fit": dict(entry.fit)},
                config=config,
            )
            scored_outputs.append(scored)
            rec_status = (
                RecordStatus.APPROVED
                if entry.status is EvaluationStatus.APPROVED
                else RecordStatus.DRAFT
            )
            ds_records.append(
                DatasetRecord(
                    character_id=entry.character_id,
                    power=scored.power,
                    fit=scored.fit,
                    scores=scored.scores,
                    status=rec_status,
                    revision_ref=entry.revision_ref,
                    scoring_version=config.version,
                )
            )

        ts = now or _utc_now()
        manifest = build_signed_manifest(
            dataset_version=dver,
            kind=kind,
            config=config,
            records=ds_records,
            governing_versions=GoverningVersions(
                universe_policy_version=universe.policy_version,
                anchor_set_version=anchor_set_version,
                calibration_set_version=calibration_set_version,
            ),
            created_at=ts,
            predecessor_version=predecessor_version,
        )
        validate_manifest_for_publication(manifest, config=config)
        health_report = build_dataset_health_report(
            dataset_version=dver,
            universe_id=universe_id,
            entries=entries,
            scored_outputs=scored_outputs,
        )

        existing_docs = list(
            self._db["published_datasets"].find(
                {"universe_id": universe_id, "kind": kind.value},
                projection={"seq": 1},
            )
        )
        max_seq = max((float(d.get("seq", 0.0)) for d in existing_docs), default=0.0)
        seq = max(time.time(), max_seq + 1e-6)
        self._db["published_datasets"].replace_one(
            {"_id": dver},
            {
                "_id": dver,
                "dataset_version": dver,
                "universe_id": universe_id,
                "kind": kind.value,
                "scoring_version": config.version,
                "manifest_json": _manifest_to_json(manifest),
                "content_hash": manifest.content_hash,
                "health_report": health_report.to_dict(),
                "rarities": {e.character_id: e.rarity for e in entries},
                "created_at": ts,
                "predecessor_version": predecessor_version,
                "seq": seq,
            },
            upsert=True,
        )
        self._manifest_cache[dver] = manifest
        self._dataset_record_cache[dver] = {rec.character_id: rec for rec in manifest.records}
        return manifest, health_report

    def load_manifest(self, dataset_version: str) -> DatasetManifest:
        cached = self._manifest_cache.get(dataset_version)
        if cached is not None:
            doc = self._db["published_datasets"].find_one({"_id": dataset_version})
            if doc is not None and doc.get("content_hash") == cached.content_hash:
                return cached
            self._manifest_cache.pop(dataset_version, None)
            self._dataset_record_cache.pop(dataset_version, None)

        doc = self._db["published_datasets"].find_one({"_id": dataset_version})
        if doc is None:
            raise DatasetValidationError(
                DatasetErrorCode.VERSION_NOT_FOUND,
                f"Dataset version {dataset_version!r} not found",
            )
        manifest = _manifest_from_json(doc["manifest_json"])
        computed = manifest.compute_content_hash()
        if manifest.content_hash != doc["content_hash"] or manifest.content_hash != computed:
            raise DatasetValidationError(
                DatasetErrorCode.HASH_MISMATCH,
                f"Content hash verification failed for dataset {dataset_version!r}",
            )
        self._manifest_cache[dataset_version] = manifest
        self._dataset_record_cache[dataset_version] = {
            rec.character_id: rec for rec in manifest.records
        }
        return manifest

    def get_character(self, dataset_version: str, character_id: str) -> DatasetRecord:
        self.load_manifest(dataset_version)
        rec = self._dataset_record_cache[dataset_version].get(character_id)
        if rec is not None:
            return rec
        raise KeyError(
            f"Character {character_id!r} not found in dataset version {dataset_version!r}"
        )

    def get_latest_published_version(
        self,
        universe_id: str,
        *,
        kind: DatasetKind = DatasetKind.PRODUCTION,
    ) -> str | None:
        docs = list(
            self._db["published_datasets"].find(
                {"universe_id": universe_id, "kind": kind.value},
                projection={"dataset_version": 1, "seq": 1},
            )
        )
        if not docs:
            return None
        docs.sort(key=lambda d: float(d.get("seq", 0.0)), reverse=True)
        return str(docs[0]["dataset_version"])

    def list_eligible_universes(
        self,
        *,
        kind: DatasetKind = DatasetKind.PRODUCTION,
    ) -> tuple[Universe, ...]:
        eligible: list[Universe] = []
        for universe in self.list_universes(active_only=True):
            if self.get_latest_published_version(universe.universe_id, kind=kind) is not None:
                eligible.append(universe)
        return tuple(eligible)

    def get_health_report(self, dataset_version: str) -> dict[str, Any]:
        doc = self._db["published_datasets"].find_one({"_id": dataset_version})
        if doc is None:
            raise DatabaseError(
                DatabaseErrorCode.VERSION_NOT_FOUND,
                f"Dataset version {dataset_version!r} not found",
            )
        return dict(doc["health_report"])

    def export_draft_catalog(
        self, dataset_version: str
    ) -> tuple[tuple[CatalogEntry, ...], dict[str, float], str]:
        manifest = self.load_manifest(dataset_version)
        doc = self._db["published_datasets"].find_one({"_id": dataset_version})
        assert doc is not None
        universe = self.get_universe(str(doc["universe_id"]))
        rarities = doc.get("rarities") or {}
        catalog = tuple(
            CatalogEntry(
                character_id=r.character_id,
                rarity_id=str(rarities.get(r.character_id) or self.get_character_entry(r.character_id).rarity),
            )
            for r in sorted(manifest.records, key=lambda rec: rec.character_id)
        )
        return catalog, dict(universe.rarity_weights), dataset_version
