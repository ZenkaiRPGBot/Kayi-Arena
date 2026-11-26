"""Validation precedence error codes and dataset access exceptions for Module 3."""

from __future__ import annotations

from enum import Enum


class ResolutionErrorCode(str, Enum):
    """Fail-fast validation error codes in exact precedence order (Section 8)."""

    MALFORMED_REQUEST = "MALFORMED_REQUEST"
    INVALID_ROLE = "INVALID_ROLE"
    INCOMPLETE_TEAM = "INCOMPLETE_TEAM"
    DUPLICATE_CHARACTER = "DUPLICATE_CHARACTER"
    DATASET_NOT_FOUND = "DATASET_NOT_FOUND"
    DATASET_UNAVAILABLE = "DATASET_UNAVAILABLE"
    DATASET_INTEGRITY_FAILURE = "DATASET_INTEGRITY_FAILURE"
    UNSUPPORTED_SCORING_VERSION = "UNSUPPORTED_SCORING_VERSION"
    CHARACTER_NOT_FOUND = "CHARACTER_NOT_FOUND"
    CHARACTER_RECORD_INVALID = "CHARACTER_RECORD_INVALID"


class DatasetUnavailableError(RuntimeError):
    """Raised by a DatasetReader on transient access failure (retryable)."""
