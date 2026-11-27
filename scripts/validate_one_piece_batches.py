"""Validate all prepared One Piece batch artefacts and cumulative files."""

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


def validate_batch(batch_id: str) -> dict[str, Any]:
    prefix = batch_id.replace("-", "_")
    catalogue = load(f"{prefix}_catalogue.json")
    research = load(f"{prefix}_research.json")
    manifest = load(f"{prefix}_image_manifest.json")
    unresolved = load(f"{prefix}_unresolved_candidates.json")
    completeness = load(f"{prefix}_completeness_report.json")
    assignment = (ROOT / f"{prefix}_claude_assignment.md").read_text(encoding="utf-8")

    catalogue_ids = {item["candidate_id"] for item in catalogue["candidates"]}
    research_ids = {item["candidate_id"] for item in research["candidates"]}
    unresolved_ids = {item["candidate_id"] for item in unresolved["candidates"]}
    assert research_ids == catalogue_ids
    assert not research_ids & unresolved_ids
    assert len(research_ids) >= 30

    cat = assess_catalogue(catalogue)
    art = assess_artwork(catalogue, manifest)
    res = assess_research(research, catalogue)
    assert cat["complete"], (batch_id, cat)
    assert art["complete"], (batch_id, art)
    assert res["complete"], (batch_id, res)
    assert completeness["stages"]["catalogue"]["complete"] is True
    assert completeness["stages"]["artwork"]["complete"] is True
    assert completeness["stages"]["research"]["complete"] is True
    assert completeness["stages"]["evaluation"]["complete"] is False
    assert completeness["stages"]["publication"]["ready"] is False

    for record in research["candidates"]:
        valid, errors = research_ready_valid(record)
        assert valid, (batch_id, record["name"], errors)
        assert record["research_gate"] == "RESEARCH_READY"
        for key in ("power", "fit", "rarity", "role_score", "approved", "approval"):
            assert key not in record

    for required in (
        research["canonical_policy"],
        "EVAL-FRAMEWORK-1.0",
        f"{prefix}_research.json",
        batch_id,
        '"captain"',
        '"healer"',
        "Ready-to-use prompt",
    ):
        assert required in assignment, (batch_id, required)

    return {
        "batch_id": batch_id,
        "research_ready": len(research_ids),
        "unresolved": len(unresolved_ids),
        "artwork_valid": manifest["summary"]["valid"],
        "catalogue": cat,
        "artwork": art,
        "research": res,
    }


def main() -> None:
    progress = load("one_piece_expansion_progress.json")
    registry = load("one_piece_master_registry.json")
    results = [validate_batch(batch_id) for batch_id in progress["batch_ids"]]

    registry_ids = {item["character_id"] for item in registry["characters"]}
    assert len(registry_ids) == registry["character_count"]
    assert sum(item["research_ready"] for item in results) == progress["totals"]["research_ready"]
    assert progress["totals"]["approved"] == 0
    assert progress["totals"]["published"] == 0
    assert all(
        item["evaluation_status"] == "not_started"
        and item["approval_status"] == "not_approved"
        for item in registry["characters"]
    )
    assert (ROOT / "one_piece_review_gallery.html").stat().st_size > 1000
    for report in (
        "ONE_PIECE_CANON_0.1.md",
        "ONE_PIECE_EXPANSION_MASTER_REPORT.md",
    ):
        assert (Path("docs") / report).stat().st_size > 100

    print(
        json.dumps(
            {
                "batches": results,
                "cumulative_ready": progress["totals"]["research_ready"],
                "registry_characters": registry["character_count"],
                "status": "validated",
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
