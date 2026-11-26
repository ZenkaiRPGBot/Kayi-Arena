"""Export the reconciled 60 Naruto characters to KA-IMPORT-1.0."""

from __future__ import annotations

import json
from pathlib import Path

from app.content.export import save_export
from app.content.models import CandidateCatalogue, CandidateCharacter, CandidateImage


def main() -> None:
    mapping = json.loads(Path("data/naruto_character_id_mapping.json").read_text(encoding="utf-8"))
    catalogue = json.loads(Path("data/naruto_candidates.json").read_text(encoding="utf-8"))
    by_id = {c["candidate_id"]: c for c in catalogue["candidates"]}

    candidates = []
    for entry in mapping["mapping"]:
        if entry["status"] != "matched":
            continue
        raw = by_id[entry["candidate_id"]]
        images = [CandidateImage(**img) for img in raw.get("images", [])]
        candidate = CandidateCharacter(
            candidate_id=raw["candidate_id"],
            name=raw["name"],
            universe=raw["universe"],
            source=raw["source"],
            source_url=raw["source_url"],
            aliases=raw.get("aliases", []),
            image_urls=raw.get("image_urls", []),
            images=images,
            debut=raw.get("debut", {}),
            classification=raw.get("classification", []),
            species=raw.get("species"),
            canonical_eligibility=raw.get("canonical_eligibility", "uncertain"),
            eligibility_reason=raw.get("eligibility_reason", ""),
            source_metadata=raw.get("source_metadata", {}),
            review_status=raw.get("review_status", "pending"),
            notes=raw.get("notes", []),
        )
        candidates.append(candidate)

    cat = CandidateCatalogue(
        universe="Naruto",
        source="dattebayo",
        provider="dattebayo",
        generated_at=__import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
        candidates=candidates,
    )
    Path("data/naruto_initial_60_catalogue.json").write_text(
        json.dumps(cat.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8"
    )
    save_export(cat, Path("data/naruto_initial_60_ka_import.json"), universe_id="naruto")
    print(f"Exported {len(candidates)} characters")


if __name__ == "__main__":
    main()
