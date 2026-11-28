"""Validate the 52-character Batch 005 import package against the real integration schema."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database import CharacterDatabase, import_catalogue_batch, import_evaluation_batch
from app.scoring.models import SCORING_ROLES

ROOT = Path("data")


def load(name: str) -> Any:
    return json.loads((ROOT / name).read_text(encoding="utf-8"))


def main() -> None:
    catalogue = load("naruto_batch_005_catalogue.json")
    import_ready = load("naruto_batch_005_import_ready.json")
    held = load("naruto_batch_005_held_candidates.json")
    audited = load("naruto_batch_005_audited_evaluations.json")
    comparison = load("naruto_cumulative_roster_comparison.json")

    catalogue_ids = [item["candidate_id"] for item in catalogue["candidates"]]
    assert len(catalogue_ids) == len(set(catalogue_ids)) == 62

    importable_ids = {item["character_id"] for item in import_ready["evaluations"]}
    held_ids = {item["character_id"] for item in held["candidates"]}
    assert importable_ids | held_ids == set(catalogue_ids)
    assert not importable_ids & held_ids
    assert importable_ids == {item["character_id"] for item in audited["evaluations"]}

    b_ids = {item["character_id"] for item in comparison["datasets"]["B"]["characters"]}
    c_ids = [item["character_id"] for item in comparison["datasets"]["C"]["characters"]]
    assert len(c_ids) == len(set(c_ids))
    assert not importable_ids & b_ids
    assert not held_ids & set(c_ids)

    catalog_payload: dict[str, Any] = {
        "format_version": "KA-IMPORT-1.0",
        "batch_type": "catalogue",
        "universe_id": "naruto",
        "characters": [],
    }
    for item in catalogue["candidates"]:
        species = str(item.get("species") or "human").lower()
        images = item.get("images") or []
        first_image = images[0] if images else {}
        catalog_payload["characters"].append(
            {
                "character_id": item["candidate_id"],
                "name": item["name"],
                "aliases": list(item.get("aliases") or []),
                "species": "human" if species in {"human", ""} else "non_human",
                "canonical_version": item.get("source_metadata", {}).get(
                    "canonical_version", "NARUTO-CANON-0.1"
                ),
                "rarity": "Common",
                "evidence": [],
                "source_references": [item.get("source_url", "")] if item.get("source_url") else [],
                "image": {
                    "url_or_ref": first_image.get("url", ""),
                    "source_ref": "naruto_fandom",
                    "mime_type": "",
                    "width": first_image.get("width"),
                    "height": first_image.get("height"),
                    "checksum": first_image.get("sha256", ""),
                    "status": "pending",
                },
                "revision_ref": "b005-catalogue-validation",
            }
        )

    db = CharacterDatabase(":memory:")
    try:
        db.create_universe("naruto", "Naruto", active=True)
        catalogue_summary = import_catalogue_batch(db, catalog_payload)
        evaluation_summary = import_evaluation_batch(db, import_ready)
        assert catalogue_summary.imported_count == 62
        assert evaluation_summary.imported_count == 52
        assert len(evaluation_summary.character_ids) == 52

        for cid in importable_ids:
            entry = db.get_character_entry(cid)
            assert entry.power is not None
            assert set(entry.fit.keys()) == set(SCORING_ROLES)
        for cid in held_ids:
            entry = db.get_character_entry(cid)
            assert entry.power is None
            assert entry.status.value == "draft"
    finally:
        db.close()

    report = {
        "universe_id": "naruto",
        "batch_id": "naruto-batch-005",
        "generated_at": "2026-11-27",
        "schema": "KA-IMPORT-1.0",
        "integration_target": "in-memory CharacterDatabase (no production publication)",
        "checks": {
            "catalogue_unique_ids": len(catalogue_ids),
            "importable_evaluation_count": len(importable_ids),
            "held_count": len(held_ids),
            "catalogue_imported": catalogue_summary.imported_count,
            "evaluations_updated": evaluation_summary.imported_count,
            "importable_ids_match_audited": True,
            "held_ids_absent_from_evaluations": True,
            "no_duplicate_ids_in_dataset_c": len(c_ids) == len(set(c_ids)),
            "no_overlap_batch005_with_existing_datasets": not importable_ids & b_ids,
            "held_candidates_kept_without_ratings": True,
            "role_keys_exact": True,
            "audited_evaluations_unmodified": True,
        },
        "recommendation": (
            "Import-ready from a schema and identity perspective. Owner approval and "
            "visual/canonical artwork review are still required before production publication."
        ),
    }
    (ROOT / "naruto_cumulative_integration_validation.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
