"""Immutable models and scoring configuration for Module 2."""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Mapping

from app.scoring.errors import ScoringConfigError, ScoringValidationErrorCode

SCORING_ROLES: tuple[str, ...] = (
    "captain",
    "strategist",
    "attacker",
    "tank",
    "assassin",
    "support",
    "healer",
)

SCORE_1_0_VERSION = "SCORE-1.0"

SCORE_1_0_PERCENT_WEIGHTS: dict[str, tuple[int, int]] = {
    "captain": (60, 40),
    "strategist": (85, 15),
    "attacker": (50, 50),
    "tank": (50, 50),
    "assassin": (65, 35),
    "support": (85, 15),
    "healer": (85, 15),
}


def is_strict_int(value: Any) -> bool:
    """Return True only for genuine int instances (rejecting bool, float, str, None)."""
    return type(value) is int


@dataclass(frozen=True, slots=True)
class RoleWeight:
    """Percentage weights and integer point multipliers for one role."""

    fit_percent: int
    power_percent: int

    def __post_init__(self) -> None:
        if not (is_strict_int(self.fit_percent) and is_strict_int(self.power_percent)):
            raise ScoringConfigError(
                "Weights must be integers", ScoringValidationErrorCode.V07
            )
        if self.fit_percent < 0 or self.power_percent < 0:
            raise ScoringConfigError(
                "Weights must be non-negative", ScoringValidationErrorCode.V07
            )
        if self.fit_percent + self.power_percent != 100:
            raise ScoringConfigError(
                "Fit and Power percent weights must sum to 100",
                ScoringValidationErrorCode.V07,
            )
        if self.fit_percent % 5 != 0 or self.power_percent % 5 != 0:
            raise ScoringConfigError(
                "Weights must be multiples of 5", ScoringValidationErrorCode.V07
            )

    @property
    def fit_points(self) -> int:
        return self.fit_percent // 5

    @property
    def power_points(self) -> int:
        return self.power_percent // 5

    @property
    def min_score(self) -> int:
        # Minimum reached at Fit=0, Power=1
        return self.power_points

    @property
    def max_score(self) -> int:
        # Maximum reached at Fit=5, Power=5
        return 5 * self.fit_points + 5 * self.power_points


@dataclass(frozen=True, slots=True)
class ScoringConfig:
    """Immutable versioned scoring configuration."""

    version: str
    weights: Mapping[str, RoleWeight]

    def __post_init__(self) -> None:
        if not isinstance(self.version, str) or not self.version.strip() or self.version != self.version.strip():
            raise ScoringConfigError(
                "Scoring version must be a non-empty trimmed string",
                ScoringValidationErrorCode.V07,
            )
        if not isinstance(self.weights, Mapping):
            raise ScoringConfigError(
                "weights must be a mapping", ScoringValidationErrorCode.V07
            )
        if set(self.weights.keys()) != set(SCORING_ROLES) or len(self.weights) != 7:
            raise ScoringConfigError(
                "Configuration must define weights for exactly the seven roles",
                ScoringValidationErrorCode.V07,
            )

        normalized: dict[str, RoleWeight] = {}
        for role in SCORING_ROLES:
            w = self.weights[role]
            if not isinstance(w, RoleWeight):
                raise ScoringConfigError(
                    f"Weight for {role!r} must be a RoleWeight instance",
                    ScoringValidationErrorCode.V07,
                )
            normalized[role] = w

        if self.version == SCORE_1_0_VERSION:
            for role, (fp, pp) in SCORE_1_0_PERCENT_WEIGHTS.items():
                w = normalized[role]
                if w.fit_percent != fp or w.power_percent != pp:
                    raise ScoringConfigError(
                        f"{SCORE_1_0_VERSION} cannot be associated with altered scoring constants",
                        ScoringValidationErrorCode.V07,
                    )

        object.__setattr__(self, "weights", MappingProxyType(normalized))


SCORE_1_0_CONFIG = ScoringConfig(
    version=SCORE_1_0_VERSION,
    weights={
        role: RoleWeight(fit_percent=fp, power_percent=pp)
        for role, (fp, pp) in SCORE_1_0_PERCENT_WEIGHTS.items()
    },
)


@dataclass(frozen=True, slots=True)
class RatingInput:
    """Optional typed rating input (dicts are equally supported)."""

    character_id: str
    power: int
    fit: Mapping[str, int]


@dataclass(frozen=True, slots=True)
class CharacterScoreOutput:
    """Immutable per-character scoring output (Section 3.3)."""

    character_id: str
    power: int
    fit: Mapping[str, int]
    scores: Mapping[str, int]
    scoring_version: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "character_id": self.character_id,
            "power": self.power,
            "fit": {role: self.fit[role] for role in SCORING_ROLES},
            "scores": {role: self.scores[role] for role in SCORING_ROLES},
            "scoring_version": self.scoring_version,
        }


@dataclass(frozen=True, slots=True)
class BatchScoreResult:
    """All-or-nothing batch scoring result."""

    accepted: bool
    results: tuple[CharacterScoreOutput, ...]
    errors: tuple[Any, ...]
    scoring_version: str
