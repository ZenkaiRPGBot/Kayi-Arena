"""Kayi Arena — Module 2: Character Evaluation & Scoring public API."""

from app.scoring.datasets import (
    DatasetKind,
    DatasetManifest,
    DatasetRecord,
    GoverningVersions,
    InMemoryDatasetRepository,
    RecordStatus,
    build_signed_manifest,
    validate_manifest_for_publication,
)
from app.scoring.diagnostics import (
    DiagnosticsReport,
    PRELIMINARY_SAMPLE_THRESHOLD,
    compute_diagnostics,
)
from app.scoring.engine import (
    score_batch,
    score_record,
    validate_record,
    verify_internal_score_range,
)
from app.scoring.errors import (
    BatchValidationError,
    DatasetErrorCode,
    DatasetValidationError,
    InternalScoreRangeError,
    ScoringConfigError,
    ScoringValidationErrorCode,
    ValidationIssue,
)
from app.scoring.models import (
    BatchScoreResult,
    CharacterScoreOutput,
    RatingInput,
    RoleWeight,
    SCORE_1_0_CONFIG,
    SCORE_1_0_PERCENT_WEIGHTS,
    SCORE_1_0_VERSION,
    SCORING_ROLES,
    ScoringConfig,
)

__all__ = [
    "BatchScoreResult",
    "BatchValidationError",
    "CharacterScoreOutput",
    "DatasetErrorCode",
    "DatasetKind",
    "DatasetManifest",
    "DatasetRecord",
    "DatasetValidationError",
    "DiagnosticsReport",
    "GoverningVersions",
    "InMemoryDatasetRepository",
    "InternalScoreRangeError",
    "PRELIMINARY_SAMPLE_THRESHOLD",
    "RatingInput",
    "RecordStatus",
    "RoleWeight",
    "SCORE_1_0_CONFIG",
    "SCORE_1_0_PERCENT_WEIGHTS",
    "SCORE_1_0_VERSION",
    "SCORING_ROLES",
    "ScoringConfig",
    "ScoringConfigError",
    "ScoringValidationErrorCode",
    "ValidationIssue",
    "build_signed_manifest",
    "compute_diagnostics",
    "score_batch",
    "score_record",
    "validate_manifest_for_publication",
    "validate_record",
    "verify_internal_score_range",
]
