"""Kayi Arena — Module 4A: Database Foundation public API."""

from app.database.errors import DatabaseError, DatabaseErrorCode
from app.database.health import DatasetHealthReport, build_dataset_health_report
from app.database.io import (
    IMPORT_FORMAT_VERSION,
    ImportSummary,
    export_published_dataset,
    export_universe_bundle,
    import_catalogue_batch,
    import_evaluation_batch,
)
from app.database.models import (
    CharacterEntry,
    DEFAULT_RARITY_WEIGHTS,
    EvaluationStatus,
    generate_dataset_version,
    EvidenceItem,
    ImageMetadata,
    ImageValidationStatus,
    RARITY_SET,
    RARITY_TIERS,
    SpeciesKind,
    Universe,
)
from app.database.naruto_loader import (
    HELD_NARUTO_NAMES,
    NarutoLoadSummary,
    bootstrap_naruto_database,
    export_approved_snapshot,
    load_naruto_60_into_db,
)
from pathlib import Path
from typing import Any

from app.database.mongo_repository import MongoCharacterDatabase
from app.database.repository import CharacterDatabase


def create_character_database(config: Any) -> CharacterDatabase | MongoCharacterDatabase:
    """Create the configured character database (SQLite default, or MongoDB Atlas)."""
    backend = str(getattr(config, "db_backend", "sqlite")).lower()
    mongo_uri = str(getattr(config, "mongodb_uri", "")).strip()
    if backend == "mongodb" and mongo_uri:
        return MongoCharacterDatabase(
            mongo_uri,
            database_name=str(getattr(config, "mongodb_database", "kayi_arena") or "kayi_arena"),
        )
    db_path = Path(str(getattr(config, "db_path", "data/kayi_arena.sqlite3")))
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return CharacterDatabase(db_path)

__all__ = [
    "CharacterDatabase",
    "MongoCharacterDatabase",
    "create_character_database",
    "CharacterEntry",
    "DEFAULT_RARITY_WEIGHTS",
    "DatabaseError",
    "DatabaseErrorCode",
    "DatasetHealthReport",
    "EvaluationStatus",
    "generate_dataset_version",
    "EvidenceItem",
    "HELD_NARUTO_NAMES",
    "IMPORT_FORMAT_VERSION",
    "ImageMetadata",
    "ImageValidationStatus",
    "ImportSummary",
    "NarutoLoadSummary",
    "RARITY_SET",
    "RARITY_TIERS",
    "SpeciesKind",
    "Universe",
    "bootstrap_naruto_database",
    "build_dataset_health_report",
    "export_approved_snapshot",
    "export_published_dataset",
    "export_universe_bundle",
    "import_catalogue_batch",
    "import_evaluation_batch",
    "load_naruto_60_into_db",
]
