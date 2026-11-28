"""Idempotency and schema validation for the Naruto Batch 005 import package.

Runs against an isolated staging SQLite database. No production database is
modified and no character is approved or published.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database import CharacterDatabase, import_catalogue_batch, import_evaluation_batch
from app.database.errors import DatabaseError
from app.database.models import EvaluationStatus
from app.scoring.models import SCORING_ROLES

ROOT = Path("data")
DEFAULT_STAGING = Path(
    os.environ.get(
        "KAYI_B005_STAGING_DB",
        r"C:\Users\2024\AppData\Local\Temp\opencode\naruto_batch_005_staging.sqlite3",
    )
)


def load(name: str) -> Any:
    return json.loads((ROOT / name).read_text(encoding="utf-8"))


def main() -> None:
    staging_path = DEFAULT_STAGING
    if staging_path.exists():
        staging_path.unlink()
    staging_path.parent.mkdir(parents=True, exist_ok=True)

    catalogue = load("naruto_batch_005_catalogue.json")
    import_ready = load("naruto_batch_005_import_ready.json")
    held = load("naruto_batch_005_held_candidates.json")
    audited = load("naruto_batch_005_audited_evaluations.json")
    rarity_by_id = {
        item["character_id"]: item["rarity"]["final_rarity"]
        for item in audited["evaluations"]
    }

    payload: dict[str, Any] = {
        "format_version": "KA-IMPORT-1.0",
        "batch_type": "catalogue",
        "universe_id": "naruto",
        "characters": [],
    }
    for item in catalogue["candidates"]:
        cid = item["candidate_id"]
        image = (item.get("images") or [{}])[0]
        species = str(item.get("species") or "human").lower()
        payload["characters"].append(
            {
                "character_id": cid,
                "name": item["name"],
                "aliases": list(item.get("aliases") or []),
                "species": "human" if species in {"human", ""} else "non_human",
                "canonical_version": item.get("source_metadata", {}).get(
                    "canonical_version", "NARUTO-CANON-0.1"
                ),
                "rarity": rarity_by_id.get(cid, "Common"),
                "evidence": [],
                "source_references": [item["source_url"]] if item.get("source_url") else [],
                "image": {
                    "url_or_ref": image.get("url", ""),
                    "source_ref": "naruto_fandom",
                    "mime_type": "",
                    "width": image.get("width"),
                    "height": image.get("height"),
                    "checksum": image.get("sha256", ""),
                    "status": "pending",
                },
                "revision_ref": "b005-catalogue-import",
            }
        )

    db = CharacterDatabase(staging_path)
    try:
        db.create_universe("naruto", "Naruto", active=True)
        first_catalogue = import_catalogue_batch(db, payload)
        count_after_first = len(db.list_characters("naruto"))

        duplicate_blocked = False
        try:
            import_catalogue_batch(db, payload)
        except DatabaseError:
            duplicate_blocked = True
        count_after_duplicate = len(db.list_characters("naruto"))

        first_eval = import_evaluation_batch(db, import_ready)
        count_after_eval = len(db.list_characters("naruto"))
        held_ids = {item["character_id"] for item in held["candidates"]}
        held_ok = all(
            db.get_character_entry(cid).power is None
            and db.get_character_entry(cid).status is EvaluationStatus.DRAFT
            for cid in held_ids
        )
        ratings_ok = all(
            db.get_character_entry(item["character_id"]).power == item["power"]
            and dict(db.get_character_entry(item["character_id"]).fit) == item["fit"]
            and set(db.get_character_entry(item["character_id"]).fit.keys()) == set(SCORING_ROLES)
            for item in import_ready["evaluations"]
        )

        repeat_error = False
        try:
            import_evaluation_batch(db, import_ready)
        except DatabaseError:
            repeat_error = True
        count_after_repeat = len(db.list_characters("naruto"))
        ratings_after_repeat_ok = all(
            db.get_character_entry(item["character_id"]).power == item["power"]
            for item in import_ready["evaluations"]
        )

        report = {
            "batch_id": "naruto-batch-005",
            "staging_database": str(staging_path),
            "production_database_modified": False,
            "catalogue_first_import": first_catalogue.imported_count,
            "characters_after_first_catalogue": count_after_first,
            "duplicate_catalogue_import_blocked": duplicate_blocked,
            "characters_after_duplicate_catalogue": count_after_duplicate,
            "evaluation_first_import": first_eval.imported_count,
            "characters_after_evaluation": count_after_eval,
            "held_candidates_without_ratings": held_ok,
            "imported_ratings_match_audited": ratings_ok,
            "repeat_evaluation_raised_schema_error": repeat_error,
            "characters_after_repeat_evaluation": count_after_repeat,
            "ratings_unchanged_after_repeat": ratings_after_repeat_ok,
            "approval_performed": False,
            "publication_performed": False,
        }
        (ROOT / "naruto_batch_005_integration_result.json").write_text(
            json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        print(json.dumps(report, indent=2))
    finally:
        db.close()


if __name__ == "__main__":
    main()
