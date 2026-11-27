"""Validate One Piece Batch 001 deliverables without network access."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.one_piece_quality import (
    assess_artwork,
    assess_catalogue,
    assess_research,
    research_ready_valid,
)

ROOT = Path("data")


def load(name: str) -> dict[str, Any]:
    return json.loads((ROOT / name).read_text(encoding="utf-8"))


def main() -> None:
    catalogue = load("one_piece_batch_001_catalogue.json")
    research = load("one_piece_batch_001_research.json")
    manifest = load("one_piece_batch_001_image_manifest.json")
    unresolved = load("one_piece_batch_001_unresolved_candidates.json")
    completeness = load("one_piece_batch_001_completeness_report.json")
    registry = load("one_piece_master_registry.json")
    progress = load("one_piece_expansion_progress.json")
    assignment = (ROOT / "one_piece_batch_001_claude_assignment.md").read_text(
        encoding="utf-8"
    )

    catalogue_ids = {item["candidate_id"] for item in catalogue["candidates"]}
    research_ids = {item["candidate_id"] for item in research["candidates"]}
    unresolved_ids = {item["candidate_id"] for item in unresolved["candidates"]}
    assert catalogue_ids == research_ids, "catalogue/research ID mismatch"
    assert not catalogue_ids & unresolved_ids, "unresolved overlaps research package"
    assert len(catalogue_ids) == len(research["candidates"])

    research_assessment = assess_research(research, catalogue)
    assert research_assessment["complete"], research_assessment
    assert not research_assessment["invalid_research_ready_records"]

    artwork_assessment = assess_artwork(catalogue, manifest)
    assert artwork_assessment["complete"], artwork_assessment

    catalogue_assessment = assess_catalogue(catalogue)
    assert catalogue_assessment["complete"], catalogue_assessment

    assert completeness["stages"]["research"]["complete"] is True
    assert completeness["stages"]["catalogue"]["complete"] is True
    assert completeness["stages"]["artwork"]["complete"] is True
    assert completeness["stages"]["evaluation"]["complete"] is False
    assert completeness["stages"]["publication"]["ready"] is False

    for record in research["candidates"]:
        valid, errors = research_ready_valid(record)
        assert valid, (record["name"], errors)
        for key in ("power", "fit", "rarity", "role_score", "approved", "approval"):
            assert key not in record, (record["name"], key)

    assert research["manga_cutoff_chapter"] == 1100
    assert research["canonical_policy"] == "ONE-PIECE-CANON-0.1"
    assert len(registry["characters"]) == 80
    assert progress["totals"]["research_ready"] == len(research["candidates"])

    for required in (
        "ONE-PIECE-CANON-0.1",
        "EVAL-FRAMEWORK-1.0",
        "one_piece_batch_001_research.json",
        '"captain"',
        '"healer"',
        "evaluation_status",
        "Ready-to-use prompt",
    ):
        assert required in assignment, required

    print(
        json.dumps(
            {
                "catalogue": catalogue_assessment,
                "artwork": artwork_assessment,
                "research": research_assessment,
                "unresolved": len(unresolved_ids),
                "registry_characters": len(registry["characters"]),
                "status": "validated",
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
