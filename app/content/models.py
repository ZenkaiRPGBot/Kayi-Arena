"""Machine-readable models for candidate character catalogues."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


REVIEW_STATUSES = ("pending", "approved", "rejected", "uncertain")
ELIGIBILITY_STATUSES = ("eligible", "uncertain", "excluded")


@dataclass
class CandidateImage:
    url: str
    source: str = "dattebayo"
    sha256: str | None = None
    format: str | None = None
    width: int | None = None
    height: int | None = None
    bytes: int | None = None
    status: str = "pending"  # pending, downloaded, valid, invalid, duplicate, missing
    error: str | None = None
    rights: str = "source-dependent; review before publication"

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None or k in {"url", "status"}}


@dataclass
class CandidateCharacter:
    candidate_id: str
    name: str
    universe: str
    source: str
    source_url: str
    aliases: list[str] = field(default_factory=list)
    image_urls: list[str] = field(default_factory=list)
    images: list[CandidateImage] = field(default_factory=list)
    debut: dict[str, Any] = field(default_factory=dict)
    classification: list[str] = field(default_factory=list)
    species: str | None = None
    canonical_eligibility: str = "uncertain"
    eligibility_reason: str = ""
    source_metadata: dict[str, Any] = field(default_factory=dict)
    review_status: str = "pending"
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["images"] = [img.to_dict() for img in self.images]
        return data


@dataclass
class CandidateCatalogue:
    universe: str
    source: str
    generated_at: str
    provider: str
    candidates: list[CandidateCharacter] = field(default_factory=list)
    duplicates_removed: list[dict[str, Any]] = field(default_factory=list)
    stats: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "universe": self.universe,
            "source": self.source,
            "provider": self.provider,
            "generated_at": self.generated_at,
            "stats": self.stats,
            "duplicates_removed": self.duplicates_removed,
            "candidates": [c.to_dict() for c in self.candidates],
        }

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> "CandidateCatalogue":
        raw = json.loads(path.read_text(encoding="utf-8"))
        catalogue = cls(
            universe=raw["universe"],
            source=raw["source"],
            provider=raw["provider"],
            generated_at=raw["generated_at"],
            stats=raw.get("stats", {}),
            duplicates_removed=raw.get("duplicates_removed", []),
        )
        for item in raw.get("candidates", []):
            images = [CandidateImage(**img) for img in item.pop("images", [])]
            candidate = CandidateCharacter(**item, images=images)
            catalogue.candidates.append(candidate)
        return catalogue


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def stable_candidate_id(source: str, raw_id: Any, name: str) -> str:
    base = f"{source}:{raw_id}:{name.strip().lower()}"
    return base
