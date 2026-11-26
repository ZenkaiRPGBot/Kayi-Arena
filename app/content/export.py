"""Export candidate catalogues to the KA-IMPORT-1.0 contract."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.content.models import CandidateCatalogue, CandidateImage

IMPORT_FORMAT_VERSION = "KA-IMPORT-1.0"
DEFAULT_PLACEHOLDER_RARITY = "Common"


def _species_value(species: str | None) -> str:
    if species and species.strip().lower() not in {"human", "none", ""}:
        return "non_human"
    return "human"


def _canonical_version(candidate) -> str:
    debut = candidate.debut or {}
    manga = debut.get("manga")
    anime = debut.get("anime")
    if isinstance(manga, str) and manga.strip():
        return manga.strip()
    if isinstance(anime, str) and anime.strip():
        return anime.strip()
    return "unknown"


def _image_status(image: CandidateImage) -> str:
    if image.status in {"missing", "invalid"}:
        return "failed"
    return "pending"


def _image_payload(image: CandidateImage) -> dict[str, Any]:
    mime = ""
    if image.format:
        mime = f"image/{image.format}"
    return {
        "url_or_ref": image.url,
        "source_ref": image.source or "",
        "mime_type": mime,
        "width": image.width,
        "height": image.height,
        "checksum": (f"sha256-{image.sha256}" if image.sha256 else ""),
        "status": _image_status(image),
    }


def _character_payload(candidate) -> dict[str, Any]:
    aliases = [a for a in (candidate.aliases or []) if a]
    # Include titles as aliases? Titles are not clean aliases; keep separate in source refs.
    source_refs = [f"source:{candidate.source}", f"profile:{candidate.source_url}"]
    if candidate.debut:
        source_refs.append(f"debut:{json.dumps(candidate.debut, sort_keys=True)}")
    image = None
    if candidate.images:
        image = _image_payload(candidate.images[0])
    elif candidate.image_urls:
        image = {
            "url_or_ref": candidate.image_urls[0],
            "source_ref": candidate.source,
            "mime_type": "",
            "width": None,
            "height": None,
            "checksum": "",
            "status": "pending",
        }
    payload = {
        "character_id": candidate.candidate_id.replace(":", "_"),
        "name": candidate.name,
        "aliases": aliases,
        "species": _species_value(candidate.species),
        "canonical_version": _canonical_version(candidate),
        # Placeholder only: final rarity is assigned during evaluation (Claude).
        "rarity": DEFAULT_PLACEHOLDER_RARITY,
        "power": None,
        "fit": None,
        "source_references": source_refs,
        "revision_ref": "cat-1",
        "review_status": candidate.review_status,
        "canonical_eligibility": candidate.canonical_eligibility,
        "eligibility_reason": candidate.eligibility_reason,
        "notes": candidate.notes,
    }
    if image is not None:
        payload["image"] = image
    return payload


def export_catalogue_batch(
    catalogue: CandidateCatalogue,
    *,
    universe_id: str | None = None,
) -> dict[str, Any]:
    uid = universe_id or catalogue.universe.lower().replace(" ", "_")
    return {
        "format_version": IMPORT_FORMAT_VERSION,
        "batch_type": "catalogue",
        "universe_id": uid,
        "characters": [_character_payload(c) for c in catalogue.candidates],
    }


def save_export(catalogue: CandidateCatalogue, path: Path, *, universe_id: str | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = export_catalogue_batch(catalogue, universe_id=universe_id)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
