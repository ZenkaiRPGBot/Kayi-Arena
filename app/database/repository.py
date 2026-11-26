"""SQLite-backed persistent Character Database & Dataset Repository (Module 4A)."""

from __future__ import annotations

import json
import math
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
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


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _validate_rarity_weights(weights: Mapping[str, float]) -> dict[str, float]:
    if set(weights.keys()) != RARITY_SET:
        raise DatabaseError(
            DatabaseErrorCode.INVALID_UNIVERSE_CONFIG,
            f"rarity_weights must contain exact keys {RARITY_TIERS}",
        )
    clean: dict[str, float] = {}
    for tier in RARITY_TIERS:
        val = float(weights[tier])
        if not math.isfinite(val) or val <= 0.0:
            raise DatabaseError(
                DatabaseErrorCode.INVALID_UNIVERSE_CONFIG,
                f"Weight for rarity {tier!r} must be a finite positive number",
            )
        clean[tier] = val
    return clean


def _manifest_to_json(manifest: DatasetManifest) -> str:
    return json.dumps(
        {
            "dataset_version": manifest.dataset_version,
            "kind": manifest.kind.value,
            "scoring_version": manifest.scoring_version,
            "records": [r.to_canonical_dict() for r in manifest.records],
            "governing_versions": manifest.governing_versions.to_dict(),
            "content_hash": manifest.content_hash,
            "created_at": manifest.created_at,
            "predecessor_version": manifest.predecessor_version,
        },
        sort_keys=True,
        separators=(",", ":"),
    )


def _manifest_from_json(raw: str) -> DatasetManifest:
    data = json.loads(raw)
    gov = data["governing_versions"]
    records = tuple(
        DatasetRecord(
            character_id=r["character_id"],
            power=r["power"],
            fit=r["fit"],
            scores=r["scores"],
            status=RecordStatus(r["status"]),
            revision_ref=r["revision_ref"],
            scoring_version=r["scoring_version"],
        )
        for r in data["records"]
    )
    return DatasetManifest(
        dataset_version=data["dataset_version"],
        kind=DatasetKind(data["kind"]),
        scoring_version=data["scoring_version"],
        records=records,
        governing_versions=GoverningVersions(
            universe_policy_version=gov["universe_policy_version"],
            anchor_set_version=gov["anchor_set_version"],
            calibration_set_version=gov["calibration_set_version"],
        ),
        content_hash=data["content_hash"],
        created_at=data["created_at"],
        predecessor_version=data.get("predecessor_version"),
    )


class CharacterDatabase:
    """Persistent SQLite character database & dataset publisher (Modules 1-3 compatible)."""

    def __init__(self, db_path: str | Path = ":memory:") -> None:
        self.db_path = str(db_path)
        if self.db_path != ":memory:":
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.db_path)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._init_schema()

    def __enter__(self) -> CharacterDatabase:
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def close(self) -> None:
        self._conn.close()

    def _init_schema(self) -> None:
        with self._conn:
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS universes (
                    universe_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    active INTEGER NOT NULL,
                    rarity_weights_json TEXT NOT NULL,
                    min_pool_size INTEGER NOT NULL,
                    policy_version TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS characters (
                    character_id TEXT PRIMARY KEY,
                    universe_id TEXT NOT NULL REFERENCES universes(universe_id),
                    name TEXT NOT NULL,
                    aliases_json TEXT NOT NULL,
                    species TEXT NOT NULL,
                    canonical_version TEXT NOT NULL,
                    rarity TEXT NOT NULL,
                    power INTEGER,
                    fit_json TEXT,
                    scores_json TEXT,
                    scoring_version TEXT,
                    evidence_json TEXT NOT NULL,
                    source_references_json TEXT NOT NULL,
                    image_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    revision_ref TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_characters_universe_status
                    ON characters(universe_id, status);

                CREATE TABLE IF NOT EXISTS published_datasets (
                    dataset_version TEXT PRIMARY KEY,
                    universe_id TEXT NOT NULL REFERENCES universes(universe_id),
                    kind TEXT NOT NULL,
                    scoring_version TEXT NOT NULL,
                    manifest_json TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    health_report_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    predecessor_version TEXT
                );

                CREATE TABLE IF NOT EXISTS published_dataset_records (
                    dataset_version TEXT NOT NULL REFERENCES published_datasets(dataset_version),
                    character_id TEXT NOT NULL,
                    rarity TEXT NOT NULL,
                    record_json TEXT NOT NULL,
                    PRIMARY KEY (dataset_version, character_id)
                );
                """
            )

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
        try:
            with self._conn:
                self._conn.execute(
                    """
                    INSERT INTO universes (
                        universe_id, name, active, rarity_weights_json,
                        min_pool_size, policy_version, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        uid,
                        uname,
                        1 if active else 0,
                        json.dumps(weights, sort_keys=True),
                        min_pool_size,
                        policy_version,
                        ts,
                        ts,
                    ),
                )
        except sqlite3.IntegrityError as exc:
            raise DatabaseError(
                DatabaseErrorCode.UNIVERSE_EXISTS,
                f"Universe {uid!r} already exists",
            ) from exc
        return self.get_universe(uid)

    def get_universe(self, universe_id: str) -> Universe:
        row = self._conn.execute(
            "SELECT * FROM universes WHERE universe_id = ?", (universe_id,)
        ).fetchone()
        if row is None:
            raise DatabaseError(
                DatabaseErrorCode.UNIVERSE_NOT_FOUND,
                f"Universe {universe_id!r} not found",
            )
        return Universe(
            universe_id=row["universe_id"],
            name=row["name"],
            active=bool(row["active"]),
            rarity_weights=json.loads(row["rarity_weights_json"]),
            min_pool_size=int(row["min_pool_size"]),
            policy_version=row["policy_version"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def list_universes(self, *, active_only: bool = False) -> tuple[Universe, ...]:
        sql = "SELECT universe_id FROM universes"
        if active_only:
            sql += " WHERE active = 1"
        sql += " ORDER BY universe_id"
        rows = self._conn.execute(sql).fetchall()
        return tuple(self.get_universe(r["universe_id"]) for r in rows)

    def set_universe_active(
        self, universe_id: str, active: bool, *, now: str | None = None
    ) -> Universe:
        self.get_universe(universe_id)
        ts = now or _utc_now()
        with self._conn:
            self._conn.execute(
                "UPDATE universes SET active = ?, updated_at = ? WHERE universe_id = ?",
                (1 if active else 0, ts, universe_id),
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
        with self._conn:
            self._conn.execute(
                "UPDATE universes SET rarity_weights_json = ?, updated_at = ? WHERE universe_id = ?",
                (json.dumps(weights, sort_keys=True), ts, universe_id),
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
            scored.power,
            {r: scored.fit[r] for r in SCORING_ROLES},
            {r: scored.scores[r] for r in SCORING_ROLES},
            scored.scoring_version,
        )

    def _row_to_character(self, row: sqlite3.Row) -> CharacterEntry:
        fit_raw = row["fit_json"]
        scores_raw = row["scores_json"]
        return CharacterEntry(
            character_id=row["character_id"],
            universe_id=row["universe_id"],
            name=row["name"],
            aliases=tuple(json.loads(row["aliases_json"])),
            species=SpeciesKind(row["species"]),
            canonical_version=row["canonical_version"],
            rarity=row["rarity"],
            power=row["power"],
            fit=json.loads(fit_raw) if fit_raw is not None else None,
            scores=json.loads(scores_raw) if scores_raw is not None else None,
            scoring_version=row["scoring_version"],
            evidence=tuple(
                EvidenceItem.from_dict(e) for e in json.loads(row["evidence_json"])
            ),
            source_references=tuple(json.loads(row["source_references_json"])),
            image=ImageMetadata.from_dict(json.loads(row["image_json"])),
            status=EvaluationStatus(row["status"]),
            revision_ref=row["revision_ref"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
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
                DatabaseErrorCode.INVALID_CHARACTER,
                "Characters in review or approved state must have complete ratings",
            )

        img = image or ImageMetadata()
        ts = now or _utc_now()
        try:
            with self._conn:
                self._conn.execute(
                    """
                    INSERT INTO characters (
                        character_id, universe_id, name, aliases_json, species,
                        canonical_version, rarity, power, fit_json, scores_json,
                        scoring_version, evidence_json, source_references_json,
                        image_json, status, revision_ref, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        cid,
                        universe_id,
                        cname,
                        json.dumps([str(a) for a in aliases]),
                        sp.value,
                        cver,
                        rarity,
                        p_val,
                        json.dumps(f_val, sort_keys=True) if f_val is not None else None,
                        json.dumps(s_val, sort_keys=True) if s_val is not None else None,
                        s_ver,
                        json.dumps([e.to_dict() for e in evidence]),
                        json.dumps([str(s) for s in source_references]),
                        json.dumps(img.to_dict(), sort_keys=True),
                        st.value,
                        revision_ref,
                        ts,
                        ts,
                    ),
                )
        except sqlite3.IntegrityError as exc:
            raise DatabaseError(
                DatabaseErrorCode.CHARACTER_EXISTS,
                f"Character {cid!r} already exists",
            ) from exc
        return self.get_character_entry(cid)

    def get_character_entry(self, character_id: str) -> CharacterEntry:
        row = self._conn.execute(
            "SELECT * FROM characters WHERE character_id = ?", (character_id,)
        ).fetchone()
        if row is None:
            raise DatabaseError(
                DatabaseErrorCode.CHARACTER_NOT_FOUND,
                f"Character {character_id!r} not found",
            )
        return self._row_to_character(row)

    def list_characters(
        self,
        universe_id: str,
        *,
        status: EvaluationStatus | None = None,
    ) -> tuple[CharacterEntry, ...]:
        self.get_universe(universe_id)
        if status is None:
            rows = self._conn.execute(
                "SELECT * FROM characters WHERE universe_id = ? ORDER BY character_id",
                (universe_id,),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM characters WHERE universe_id = ? AND status = ? ORDER BY character_id",
                (universe_id, status.value),
            ).fetchall()
        return tuple(self._row_to_character(r) for r in rows)

    def update_character_evaluation(
        self,
        character_id: str,
        *,
        power: int,
        fit: Mapping[str, int],
        evidence: Sequence[EvidenceItem] | None = None,
        source_references: Sequence[str] | None = None,
        revision_ref: str | None = None,
        config: ScoringConfig = SCORE_1_0_CONFIG,
        now: str | None = None,
    ) -> CharacterEntry:
        existing = self.get_character_entry(character_id)
        if existing.status is EvaluationStatus.APPROVED:
            raise DatabaseError(
                DatabaseErrorCode.INVALID_TRANSITION,
                "Approved character must be reopened to draft before editing evaluation",
            )
        p_val, f_val, s_val, s_ver = self._validate_and_score_ratings(
            character_id, power, fit, config
        )
        ev = existing.evidence if evidence is None else tuple(evidence)
        refs = existing.source_references if source_references is None else tuple(source_references)
        rev = revision_ref or existing.revision_ref
        ts = now or _utc_now()
        with self._conn:
            self._conn.execute(
                """
                UPDATE characters
                SET power = ?, fit_json = ?, scores_json = ?, scoring_version = ?,
                    evidence_json = ?, source_references_json = ?, revision_ref = ?,
                    updated_at = ?
                WHERE character_id = ?
                """,
                (
                    p_val,
                    json.dumps(f_val, sort_keys=True),
                    json.dumps(s_val, sort_keys=True),
                    s_ver,
                    json.dumps([e.to_dict() for e in ev]),
                    json.dumps(list(refs)),
                    rev,
                    ts,
                    character_id,
                ),
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
        with self._conn:
            self._conn.execute(
                "UPDATE characters SET image_json = ?, updated_at = ? WHERE character_id = ?",
                (json.dumps(image.to_dict(), sort_keys=True), ts, character_id),
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
                f"Cannot submit for review from {entry.status.value!r}",
            )
        p_val, f_val, s_val, s_ver = self._validate_and_score_ratings(
            entry.character_id, entry.power, entry.fit, config
        )
        if p_val is None or f_val is None:
            raise DatabaseError(
                DatabaseErrorCode.INVALID_TRANSITION,
                "Incomplete candidate record cannot move to review",
            )
        ts = now or _utc_now()
        with self._conn:
            self._conn.execute(
                "UPDATE characters SET status = ?, scores_json = ?, scoring_version = ?, updated_at = ? WHERE character_id = ?",
                (
                    EvaluationStatus.REVIEW.value,
                    json.dumps(s_val, sort_keys=True),
                    s_ver,
                    ts,
                    character_id,
                ),
            )
        return self.get_character_entry(character_id)

    def approve_character(
        self,
        character_id: str,
        *,
        config: ScoringConfig = SCORE_1_0_CONFIG,
        now: str | None = None,
    ) -> CharacterEntry:
        entry = self.get_character_entry(character_id)
        if entry.status is not EvaluationStatus.REVIEW:
            raise DatabaseError(
                DatabaseErrorCode.INVALID_TRANSITION,
                f"Character must be in 'review' state before approval (got {entry.status.value!r})",
            )
        p_val, f_val, s_val, s_ver = self._validate_and_score_ratings(
            entry.character_id, entry.power, entry.fit, config
        )
        if p_val is None or f_val is None:
            raise DatabaseError(
                DatabaseErrorCode.INVALID_TRANSITION,
                "Cannot approve character without valid ratings",
            )
        ts = now or _utc_now()
        with self._conn:
            self._conn.execute(
                "UPDATE characters SET status = ?, scores_json = ?, scoring_version = ?, updated_at = ? WHERE character_id = ?",
                (
                    EvaluationStatus.APPROVED.value,
                    json.dumps(s_val, sort_keys=True),
                    s_ver,
                    ts,
                    character_id,
                ),
            )
        return self.get_character_entry(character_id)

    def reopen_to_draft(
        self, character_id: str, *, now: str | None = None
    ) -> CharacterEntry:
        entry = self.get_character_entry(character_id)
        if entry.status is EvaluationStatus.DRAFT:
            return entry
        ts = now or _utc_now()
        with self._conn:
            self._conn.execute(
                "UPDATE characters SET status = ?, updated_at = ? WHERE character_id = ?",
                (EvaluationStatus.DRAFT.value, ts, character_id),
            )
        return self.get_character_entry(character_id)

    # ------------------------------------------------------------------
    # Dataset publication, integrity verification & M1-M3 integration
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
        if self._conn.execute(
            "SELECT 1 FROM published_datasets WHERE dataset_version = ?", (dver,)
        ).fetchone():
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
                    f"Character {entry.character_id!r} lacks complete ratings",
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

        with self._conn:
            self._conn.execute(
                """
                INSERT INTO published_datasets (
                    dataset_version, universe_id, kind, scoring_version,
                    manifest_json, content_hash, health_report_json,
                    created_at, predecessor_version
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    dver,
                    universe_id,
                    kind.value,
                    config.version,
                    _manifest_to_json(manifest),
                    manifest.content_hash,
                    json.dumps(health_report.to_dict(), sort_keys=True),
                    ts,
                    predecessor_version,
                ),
            )
            for entry, ds_rec in zip(entries, ds_records):
                self._conn.execute(
                    """
                    INSERT INTO published_dataset_records (
                        dataset_version, character_id, rarity, record_json
                    ) VALUES (?, ?, ?, ?)
                    """,
                    (
                        dver,
                        ds_rec.character_id,
                        entry.rarity,
                        json.dumps(ds_rec.to_canonical_dict(), sort_keys=True),
                    ),
                )

        return manifest, health_report

    def load_manifest(self, dataset_version: str) -> DatasetManifest:
        """Module 3 DatasetReader contract: load & verify content hash on every read."""
        row = self._conn.execute(
            "SELECT manifest_json, content_hash FROM published_datasets WHERE dataset_version = ?",
            (dataset_version,),
        ).fetchone()
        if row is None:
            raise DatasetValidationError(
                DatasetErrorCode.VERSION_NOT_FOUND,
                f"Dataset version {dataset_version!r} not found",
            )
        manifest = _manifest_from_json(row["manifest_json"])
        computed = manifest.compute_content_hash()
        if manifest.content_hash != row["content_hash"] or manifest.content_hash != computed:
            raise DatasetValidationError(
                DatasetErrorCode.HASH_MISMATCH,
                f"Content hash verification failed for dataset {dataset_version!r}",
            )
        return manifest

    def get_character(self, dataset_version: str, character_id: str) -> DatasetRecord:
        """Module 3 DatasetReader contract: fetch character from verified pinned version."""
        manifest = self.load_manifest(dataset_version)
        for rec in manifest.records:
            if rec.character_id == character_id:
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
        """Return the most recently published dataset_version for ``universe_id``, if any."""
        row = self._conn.execute(
            """
            SELECT dataset_version
            FROM published_datasets
            WHERE universe_id = ? AND kind = ?
            ORDER BY rowid DESC
            LIMIT 1
            """,
            (universe_id, kind.value),
        ).fetchone()
        return row["dataset_version"] if row is not None else None

    def list_eligible_universes(
        self,
        *,
        kind: DatasetKind = DatasetKind.PRODUCTION,
    ) -> tuple[Universe, ...]:
        """Return active universes that have at least one published dataset of ``kind``."""
        eligible: list[Universe] = []
        for universe in self.list_universes(active_only=True):
            if self.get_latest_published_version(universe.universe_id, kind=kind) is not None:
                eligible.append(universe)
        return tuple(eligible)

    def get_health_report(self, dataset_version: str) -> dict[str, Any]:
        row = self._conn.execute(
            "SELECT health_report_json FROM published_datasets WHERE dataset_version = ?",
            (dataset_version,),
        ).fetchone()
        if row is None:
            raise DatabaseError(
                DatabaseErrorCode.VERSION_NOT_FOUND,
                f"Dataset version {dataset_version!r} not found",
            )
        return json.loads(row["health_report_json"])

    def export_draft_catalog(
        self, dataset_version: str
    ) -> tuple[tuple[CatalogEntry, ...], dict[str, float], str]:
        """Module 1 boundary: export (catalog, rarity_weights, dataset_version)."""
        self.load_manifest(dataset_version)
        ds_row = self._conn.execute(
            "SELECT universe_id FROM published_datasets WHERE dataset_version = ?",
            (dataset_version,),
        ).fetchone()
        assert ds_row is not None
        universe = self.get_universe(ds_row["universe_id"])
        rec_rows = self._conn.execute(
            "SELECT character_id, rarity FROM published_dataset_records WHERE dataset_version = ? ORDER BY character_id",
            (dataset_version,),
        ).fetchall()
        catalog = tuple(
            CatalogEntry(character_id=r["character_id"], rarity_id=r["rarity"])
            for r in rec_rows
        )
        return catalog, dict(universe.rarity_weights), dataset_version
