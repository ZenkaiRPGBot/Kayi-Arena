"""Validation error codes and exceptions for Module 2 (Evaluation & Scoring)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ScoringValidationErrorCode(str, Enum):
    """Validation codes V01-V08 defined by Module 2 Final Spec Section 3.5."""

    V01 = "V01"  # Missing required field or unknown field
    V02 = "V02"  # power or any Fit value is not an integer type
    V03 = "V03"  # power outside 1-5
    V04 = "V04"  # fit keys are not exactly the seven roles
    V05 = "V05"  # any Fit value outside 0-5
    V06 = "V06"  # character_id empty or duplicated within the batch
    V07 = "V07"  # configuration invalid
    V08 = "V08"  # computed score outside role min-100 range (internal guard)


class DatasetErrorCode(str, Enum):
    """Dataset version and integrity error codes (DV1-DV8)."""

    NON_APPROVED_IN_PRODUCTION = "NON_APPROVED_IN_PRODUCTION"
    VERSION_IMMUTABLE = "VERSION_IMMUTABLE"
    HASH_MISMATCH = "HASH_MISMATCH"
    SCORE_MISMATCH = "SCORE_MISMATCH"
    VERSION_NOT_FOUND = "VERSION_NOT_FOUND"
    DUPLICATE_CHARACTER = "DUPLICATE_CHARACTER"
    MIXED_SCORING_VERSION = "MIXED_SCORING_VERSION"
    INVALID_MANIFEST = "INVALID_MANIFEST"


@dataclass(frozen=True, slots=True)
class ValidationIssue:
    """Structured validation error for single-record or all-or-nothing batch scoring."""

    record_id: str | None
    code: ScoringValidationErrorCode
    message: str


class ScoringConfigError(ValueError):
    """Raised when a ScoringConfig violates V07."""

    def __init__(self, message: str, code: ScoringValidationErrorCode = ScoringValidationErrorCode.V07) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class BatchValidationError(ValueError):
    """Raised by single-record or strict scoring when validation fails."""

    def __init__(self, issues: tuple[ValidationIssue, ...]) -> None:
        summary = "; ".join(f"{i.code.value}({i.record_id}): {i.message}" for i in issues)
        super().__init__(summary)
        self.issues = issues


class InternalScoreRangeError(RuntimeError):
    """Internal V08 guard: computed score fell outside [role_min, 100]."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.code = ScoringValidationErrorCode.V08


class DatasetValidationError(ValueError):
    """Raised when dataset manifest publication or verification fails."""

    def __init__(self, code: DatasetErrorCode, message: str) -> None:
        super().__init__(f"{code.value}: {message}")
        self.code = code
        self.message = message
