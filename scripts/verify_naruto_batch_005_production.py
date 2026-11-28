"""Verify available production/draft roster state and Batch 005 artwork/overlap."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database import CharacterDatabase
from app.database.models import EvaluationStatus
from app.scoring import DatasetKind

ROOT = Path("data")


def load(name: str) -> Any:
    return json.loads((ROOT / name).read_text(encoding="utf-8"))


def main() -> None:
    db_path = Path(os.environ.get("ARENA_DB_PATH", str(ROOT / "kayi_arena.sqlite3")))
    live_available = db_path.exists()
    live: dict[str, Any] = {
        "database_path": str(db_path),
        "available": live_available,
    }
    if live_available:
        db = CharacterDatabase(db_path)
        try:
            characters = db.list_characters("naruto")
            live.update(
                {
                    "published_character_count": sum(
                        1 for c in characters if c.status is EvaluationStatus.APPROVED
                    ),
                    "pending_character_count": sum(
                        1 for c in characters if c.status is not EvaluationStatus.APPROVED
                    ),
                    "draft_count": sum(
                        1 for c in characters if c.status is EvaluationStatus.DRAFT
                    ),
                    "review_count": sum(
                        1 for c in characters if c.status is EvaluationStatus.REVIEW
                    ),
                    "current_dataset_version": db.get_latest_published_version(
                        "naruto", kind=DatasetKind.PRODUCTION
                    ),
                    "character_ids": sorted(c.character_id for c in characters),
                }
            )
        finally:
            db.close()
    else:
        live.update(
            {
                "published_character_count": None,
                "pending_character_count": None,
                "draft_count": None,
                "review_count": None,
                "current_dataset_version": None,
                "character_ids": [],
                "note": "No live SQLite database file found in the workspace; production counts are unavailable.",
            }
        )

    initial = load("naruto_evaluated_60_dataset.json")["characters"]
    expansion = load("naruto_expansion_003_004_evaluated_dataset.json")["characters"]
    batch_ids = {
        item["candidate_id"] for item in load("naruto_batch_005_catalogue.json")["candidates"]
    }
    reconstructed_ids = {
        item["character_id"]
        for item in initial + expansion
        if not item.get("held") and item.get("evaluation_status") != "held"
    }
    overlap = sorted(batch_ids & reconstructed_ids)

    manifest = load("naruto_batch_005_image_manifest.json")
    report = {
        "batch_id": "naruto-batch-005",
        "live_database": live,
        "reconstructed_draft_snapshot": {
            "initial_60_records": len(initial),
            "initial_60_held": sum(1 for c in initial if c.get("held")),
            "expansion_003_004_records": len(expansion),
            "expansion_003_004_held": sum(1 for c in expansion if c.get("held")),
            "non_held_unique_characters": len(reconstructed_ids),
            "verified_published_snapshot": False,
        },
        "batch_005": {
            "catalogue_candidates": len(batch_ids),
            "importable_evaluations": len(load("naruto_batch_005_import_ready.json")["evaluations"]),
            "held_candidates": len(load("naruto_batch_005_held_candidates.json")["candidates"]),
            "overlap_with_reconstructed_ids": overlap,
            "artwork_summary": manifest["summary"],
        },
        "expected_reconstructed_roster_after_publication": len(reconstructed_ids) + len(
            load("naruto_batch_005_import_ready.json")["evaluations"]
        ),
        "publication_performed": False,
    }
    (ROOT / "naruto_batch_005_production_verification.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
