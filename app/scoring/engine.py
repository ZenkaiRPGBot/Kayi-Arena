"""Pure deterministic integer scoring engine (Module 2 Section 3)."""

from __future__ import annotations

from types import MappingProxyType
from typing import Any, Mapping, Sequence

from app.scoring.errors import (
    BatchValidationError,
    InternalScoreRangeError,
    ScoringValidationErrorCode,
    ValidationIssue,
)
from app.scoring.models import (
    BatchScoreResult,
    CharacterScoreOutput,
    RatingInput,
    RoleWeight,
    SCORE_1_0_CONFIG,
    SCORING_ROLES,
    ScoringConfig,
    is_strict_int,
)

_REQUIRED_FIELDS = frozenset({"character_id", "power", "fit"})
_ROLE_SET = frozenset(SCORING_ROLES)


def _extract_fields(
    record: Mapping[str, Any] | RatingInput,
) -> tuple[dict[str, Any] | None, list[ValidationIssue]]:
    if isinstance(record, RatingInput):
        return {
            "character_id": record.character_id,
            "power": record.power,
            "fit": record.fit,
        }, []
    if not isinstance(record, Mapping):
        return None, [
            ValidationIssue(
                record_id=None,
                code=ScoringValidationErrorCode.V01,
                message="Record must be a mapping or RatingInput",
            )
        ]
    keys = set(record.keys())
    missing = _REQUIRED_FIELDS - keys
    unknown = keys - _REQUIRED_FIELDS
    if missing or unknown:
        raw_id = record.get("character_id")
        rec_id = raw_id if isinstance(raw_id, str) and raw_id else None
        parts = []
        if missing:
            parts.append(f"missing {sorted(missing)}")
        if unknown:
            parts.append(f"unknown {sorted(unknown)}")
        return None, [
            ValidationIssue(
                record_id=rec_id,
                code=ScoringValidationErrorCode.V01,
                message=", ".join(parts),
            )
        ]
    return dict(record), []


def validate_record(
    record: Mapping[str, Any] | RatingInput,
    *,
    seen_ids: set[str] | None = None,
) -> tuple[dict[str, Any] | None, list[ValidationIssue]]:
    """Validate one rating record against rules V01-V06 without mutating it."""
    fields, issues = _extract_fields(record)
    if fields is None:
        return None, issues

    raw_id = fields["character_id"]
    rec_id: str | None = raw_id if isinstance(raw_id, str) and raw_id.strip() else None
    if not isinstance(raw_id, str) or not raw_id.strip():
        issues.append(
            ValidationIssue(
                record_id=None,
                code=ScoringValidationErrorCode.V06,
                message="character_id must be a non-empty string",
            )
        )
    else:
        if seen_ids is not None:
            if raw_id in seen_ids:
                issues.append(
                    ValidationIssue(
                        record_id=raw_id,
                        code=ScoringValidationErrorCode.V06,
                        message=f"Duplicate character_id {raw_id!r} within batch",
                    )
                )
            else:
                seen_ids.add(raw_id)

    power = fields["power"]
    if not is_strict_int(power):
        issues.append(
            ValidationIssue(
                record_id=rec_id,
                code=ScoringValidationErrorCode.V02,
                message="power must be an integer (not float, bool, str, or null)",
            )
        )
    elif not (1 <= power <= 5):
        issues.append(
            ValidationIssue(
                record_id=rec_id,
                code=ScoringValidationErrorCode.V03,
                message=f"power {power} outside valid range 1-5",
            )
        )

    fit = fields["fit"]
    if not isinstance(fit, Mapping):
        issues.append(
            ValidationIssue(
                record_id=rec_id,
                code=ScoringValidationErrorCode.V04,
                message="fit must be a mapping keyed by the seven roles",
            )
        )
    else:
        if set(fit.keys()) != _ROLE_SET:
            issues.append(
                ValidationIssue(
                    record_id=rec_id,
                    code=ScoringValidationErrorCode.V04,
                    message="fit keys must be exactly the seven roles",
                )
            )
        else:
            for role in SCORING_ROLES:
                val = fit[role]
                if not is_strict_int(val):
                    issues.append(
                        ValidationIssue(
                            record_id=rec_id,
                            code=ScoringValidationErrorCode.V02,
                            message=f"fit[{role!r}] must be an integer",
                        )
                    )
                elif not (0 <= val <= 5):
                    issues.append(
                        ValidationIssue(
                            record_id=rec_id,
                            code=ScoringValidationErrorCode.V05,
                            message=f"fit[{role!r}] value {val} outside valid range 0-5",
                        )
                    )

    if issues:
        return None, issues
    return fields, []


def verify_internal_score_range(
    score: int,
    *,
    role: str,
    weight: RoleWeight,
) -> int:
    """Internal V08 invariant guard (unreachable with valid inputs & config)."""
    if not (weight.min_score <= score <= weight.max_score):
        raise InternalScoreRangeError(
            f"Computed score {score} for {role!r} outside [{weight.min_score}, {weight.max_score}]"
        )
    return score


def _compute_record(
    fields: Mapping[str, Any],
    config: ScoringConfig,
) -> CharacterScoreOutput:
    power: int = fields["power"]
    fit_in: Mapping[str, int] = fields["fit"]
    fit_out: dict[str, int] = {}
    scores_out: dict[str, int] = {}

    for role in SCORING_ROLES:
        fit_val = fit_in[role]
        w = config.weights[role]
        score = fit_val * w.fit_points + power * w.power_points
        verify_internal_score_range(score, role=role, weight=w)
        fit_out[role] = fit_val
        scores_out[role] = score

    return CharacterScoreOutput(
        character_id=fields["character_id"],
        power=power,
        fit=MappingProxyType(fit_out),
        scores=MappingProxyType(scores_out),
        scoring_version=config.version,
    )


def score_record(
    record: Mapping[str, Any] | RatingInput,
    config: ScoringConfig = SCORE_1_0_CONFIG,
) -> CharacterScoreOutput:
    """Validate and score a single character rating record."""
    fields, issues = validate_record(record)
    if issues or fields is None:
        raise BatchValidationError(tuple(issues))
    return _compute_record(fields, config)


def score_batch(
    records: Sequence[Mapping[str, Any] | RatingInput],
    config: ScoringConfig = SCORE_1_0_CONFIG,
) -> BatchScoreResult:
    """Validate and score a batch atomically (all-or-nothing)."""
    seen_ids: set[str] = set()
    all_issues: list[ValidationIssue] = []
    parsed_records: list[dict[str, Any]] = []

    for rec in records:
        fields, issues = validate_record(rec, seen_ids=seen_ids)
        if issues:
            all_issues.extend(issues)
        elif fields is not None:
            parsed_records.append(fields)

    if all_issues:
        return BatchScoreResult(
            accepted=False,
            results=(),
            errors=tuple(all_issues),
            scoring_version=config.version,
        )

    outputs = tuple(_compute_record(fields, config) for fields in parsed_records)
    return BatchScoreResult(
        accepted=True,
        results=outputs,
        errors=(),
        scoring_version=config.version,
    )
