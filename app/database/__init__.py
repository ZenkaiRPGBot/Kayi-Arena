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
    EvidenceItem,
    ImageMetadata,
    ImageValidationStatus,
    RARITY_SET,
    RARITY_TIERS,
    SpeciesKind,
    Universe,
)
from app.database.repository import CharacterDatabase

__all__ = [
    "CharacterDatabase",
    "CharacterEntry",
    "DEFAULT_RARITY_WEIGHTS",
    "DatabaseError",
    "DatabaseErrorCode",
    "DatasetHealthReport",
    "EvaluationStatus",
    "EvidenceItem",
    "IMPORT_FORMAT_VERSION",
    "ImageMetadata",
    "ImageValidationStatus",
    "ImportSummary",
    "RARITY_SET",
    "RARITY_TIERS",
    "SpeciesKind",
    "Universe",
    "build_dataset_health_report",
    "export_published_dataset",
    "export_universe_bundle",
    "import_catalogue_batch",
    "import_evaluation_batch",
]
