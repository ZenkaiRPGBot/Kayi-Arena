"""Catalogue building, deduplication, and reporting helpers."""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from app.content.models import CandidateCatalogue, CandidateCharacter, utc_now


def _normalize_name(name: str) -> str:
    return " ".join(name.strip().lower().split())


def deduplicate_candidates(
    candidates: list[CandidateCharacter],
) -> tuple[list[CandidateCharacter], list[dict[str, Any]]]:
    """Deduplicate by candidate id and normalized name, preserving first occurrence."""

    seen_ids: set[str] = set()
    seen_names: set[str] = set()
    unique: list[CandidateCharacter] = []
    duplicates: list[dict[str, Any]] = []

    for candidate in candidates:
        normalized = _normalize_name(candidate.name)
        if candidate.candidate_id in seen_ids or normalized in seen_names:
            duplicates.append(
                {
                    "candidate_id": candidate.candidate_id,
                    "name": candidate.name,
                    "duplicate_of": next(
                        (
                            c.candidate_id
                            for c in unique
                            if _normalize_name(c.name) == normalized or c.candidate_id == candidate.candidate_id
                        ),
                        None,
                    ),
                    "reason": "duplicate candidate id or normalized name",
                }
            )
            continue
        seen_ids.add(candidate.candidate_id)
        seen_names.add(normalized)
        unique.append(candidate)

    return unique, duplicates


def build_catalogue(
    *,
    universe: str,
    provider_name: str,
    source: str,
    candidates: list[CandidateCharacter],
) -> CandidateCatalogue:
    unique, duplicates = deduplicate_candidates(candidates)
    stats = {
        "total_discovered": len(candidates),
        "unique_candidates": len(unique),
        "duplicates_removed": len(duplicates),
        "with_images": sum(1 for c in unique if c.image_urls),
        "without_images": sum(1 for c in unique if not c.image_urls),
        "uncertain_eligibility": sum(1 for c in unique if c.canonical_eligibility != "eligible"),
        "boruto_candidates": sum(1 for c in unique if c.universe == "Boruto"),
        "naruto_candidates": sum(1 for c in unique if c.universe == "Naruto"),
        "image_url_count": sum(len(c.image_urls) for c in unique),
    }
    return CandidateCatalogue(
        universe=universe,
        source=source,
        generated_at=utc_now(),
        provider=provider_name,
        candidates=unique,
        duplicates_removed=duplicates,
        stats=stats,
    )


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
