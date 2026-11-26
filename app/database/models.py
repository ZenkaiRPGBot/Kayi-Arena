"""Immutable domain models for Module 4A (Character Database & Dataset Management)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType
from typing import Any, Mapping

from app.scoring import SCORING_ROLES

RARITY_TIERS: tuple[str, ...] = (
    "Common",
    "Uncommon",
    "Rare",
    "Epic",
    "Legendary",
)
RARITY_SET: frozenset[str] = frozenset(RARITY_TIERS)

DEFAULT_RARITY_WEIGHTS: dict[str, float] = {
    "Common": 30.0,
    "Uncommon": 30.0,
    "Rare": 22.0,
    "Epic": 13.0,
    "Legendary": 5.0,
}


class EvaluationStatus(str, Enum):
    DRAFT = "draft"
    REVIEW = "review"
    APPROVED = "approved"


class ImageValidationStatus(str, Enum):
    PENDING = "pending"
    VERIFIED = "verified"
    FAILED = "failed"


class SpeciesKind(str, Enum):
    HUMAN = "human"
    NON_HUMAN = "non_human"


@dataclass(frozen=True, slots=True)
class Universe:
    """Anime universe configuration and activation state."""

    universe_id: str
    name: str
    active: bool
    rarity_weights: Mapping[str, float]
    min_pool_size: int
    policy_version: str
    created_at: str
    updated_at: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "rarity_weights",
            MappingProxyType({r: float(self.rarity_weights[r]) for r in RARITY_TIERS}),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "universe_id": self.universe_id,
            "name": self.name,
            "active": self.active,
            "rarity_weights": {r: self.rarity_weights[r] for r in RARITY_TIERS},
            "min_pool_size": self.min_pool_size,
            "policy_version": self.policy_version,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass(frozen=True, slots=True)
class ImageMetadata:
    """Character image metadata & validation status (no external downloading)."""

    url_or_ref: str = ""
    source_ref: str = ""
    mime_type: str = ""
    width: int | None = None
    height: int | None = None
    checksum: str = ""
    status: ImageValidationStatus = ImageValidationStatus.PENDING

    def to_dict(self) -> dict[str, Any]:
        return {
            "url_or_ref": self.url_or_ref,
            "source_ref": self.source_ref,
            "mime_type": self.mime_type,
            "width": self.width,
            "height": self.height,
            "checksum": self.checksum,
            "status": self.status.value,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> ImageMetadata:
        return cls(
            url_or_ref=str(data.get("url_or_ref", "")),
            source_ref=str(data.get("source_ref", "")),
            mime_type=str(data.get("mime_type", "")),
            width=data.get("width"),
            height=data.get("height"),
            checksum=str(data.get("checksum", "")),
            status=ImageValidationStatus(data.get("status", ImageValidationStatus.PENDING.value)),
        )


@dataclass(frozen=True, slots=True)
class EvidenceItem:
    """Canonical evaluation evidence item attached to a character rating."""

    target: str
    grade: str
    source_ref: str
    summary: str

    def to_dict(self) -> dict[str, str]:
        return {
            "target": self.target,
            "grade": self.grade,
            "source_ref": self.source_ref,
            "summary": self.summary,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> EvidenceItem:
        return cls(
            target=str(data["target"]),
            grade=str(data["grade"]),
            source_ref=str(data.get("source_ref", "")),
            summary=str(data.get("summary", "")),
        )


@dataclass(frozen=True, slots=True)
class CharacterEntry:
    """Persistent character catalogue & evaluation record (one canonical version)."""

    character_id: str
    universe_id: str
    name: str
    aliases: tuple[str, ...]
    species: SpeciesKind
    canonical_version: str
    rarity: str
    power: int | None
    fit: Mapping[str, int] | None
    scores: Mapping[str, int] | None
    scoring_version: str | None
    evidence: tuple[EvidenceItem, ...]
    source_references: tuple[str, ...]
    image: ImageMetadata
    status: EvaluationStatus
    revision_ref: str
    created_at: str
    updated_at: str

    def __post_init__(self) -> None:
        if self.fit is not None:
            object.__setattr__(
                self,
                "fit",
                MappingProxyType({r: int(self.fit[r]) for r in SCORING_ROLES}),
            )
        if self.scores is not None:
            object.__setattr__(
                self,
                "scores",
                MappingProxyType({r: int(self.scores[r]) for r in SCORING_ROLES}),
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "character_id": self.character_id,
            "universe_id": self.universe_id,
            "name": self.name,
            "aliases": list(self.aliases),
            "species": self.species.value,
            "canonical_version": self.canonical_version,
            "rarity": self.rarity,
            "power": self.power,
            "fit": {r: self.fit[r] for r in SCORING_ROLES} if self.fit is not None else None,
            "scores": (
                {r: self.scores[r] for r in SCORING_ROLES} if self.scores is not None else None
            ),
            "scoring_version": self.scoring_version,
            "evidence": [e.to_dict() for e in self.evidence],
            "source_references": list(self.source_references),
            "image": self.image.to_dict(),
            "status": self.status.value,
            "revision_ref": self.revision_ref,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
