"""Focused integration tests for Naruto Batch 005."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path("data")


def load(name: str):
    return json.loads((ROOT / name).read_text(encoding="utf-8"))


def test_all_62_candidates_accounted_for() -> None:
    importable = load("naruto_batch_005_import_ready.json")["evaluations"]
    held = load("naruto_batch_005_held_candidates.json")["candidates"]
    audit_details = load("naruto_batch_005_audit_details.json")["candidates"]
    assert len(importable) == 52
    assert len(held) == 10
    assert len(audit_details) == 62
    assert {e["character_id"] for e in importable} | {c["character_id"] for c in held} == {
        e["character_id"] for e in audit_details
    }


def test_held_candidates_are_not_importable() -> None:
    importable_ids = {e["character_id"] for e in load("naruto_batch_005_import_ready.json")["evaluations"]}
    held = load("naruto_batch_005_held_candidates.json")["candidates"]
    for item in held:
        assert item["character_id"] not in importable_ids
        assert item["power"] is None and item["fit"] is None
        assert item["reason"]


def test_staging_import_result() -> None:
    result = load("naruto_batch_005_integration_result.json")
    assert result["catalogue_first_import"] == 62
    assert result["duplicate_catalogue_import_blocked"] is True
    assert result["characters_after_duplicate_catalogue"] == 62
    assert result["evaluation_first_import"] == 52
    assert result["characters_after_evaluation"] == 62
    assert result["held_candidates_without_ratings"] is True
    assert result["imported_ratings_match_audited"] is True
    assert result["characters_after_repeat_evaluation"] == 62
    assert result["ratings_unchanged_after_repeat"] is True
    assert result["production_database_modified"] is False
    assert result["approval_performed"] is False
    assert result["publication_performed"] is False


def test_production_verification_limitations() -> None:
    report = load("naruto_batch_005_production_verification.json")
    live = report["live_database"]
    assert live["available"] is False
    assert live["published_character_count"] is None
    assert live["current_dataset_version"] is None
    assert report["reconstructed_draft_snapshot"]["non_held_unique_characters"] == 184
    assert report["batch_005"]["overlap_with_reconstructed_ids"] == []
    assert report["expected_reconstructed_roster_after_publication"] == 236
    assert report["publication_performed"] is False


def test_artwork_availability() -> None:
    report = load("naruto_batch_005_production_verification.json")
    artwork = report["batch_005"]["artwork_summary"]
    assert artwork["candidates_total"] == 62
    assert artwork["candidates_with_valid_artwork"] == 62
    assert artwork["invalid"] == 0 and artwork["missing"] == 0
    assert artwork["duplicates"] == 0


def test_no_specialist_candidates_identified() -> None:
    comparison = load("naruto_cumulative_roster_comparison.json")
    roles = ("captain", "strategist", "attacker", "tank", "assassin", "support", "healer")
    weak = [
        item["name"]
        for item in comparison["datasets"]["C"]["characters"]
        if all(item["fit"][role] <= 1 for role in roles)
    ]
    assert len(weak) == 33
    assert all(item["batch"] == "005_audited" for item in comparison["datasets"]["C"]["characters"] if item["name"] in weak)


def test_documented_fit_zero_maxima() -> None:
    text = (Path("docs") / "NARUTO_SIMULATION_INTEGRITY_AUDIT_REPORT.md").read_text(encoding="utf-8")
    for phrase in ("Captain 40", "Strategist 15", "Attacker 50", "Tank 50", "Assassin 35", "Support 15", "Healer 15"):
        assert phrase in text


def test_integration_report_exists() -> None:
    report = Path("docs") / "NARUTO_BATCH_005_INTEGRATION_REPORT.md"
    assert report.exists()
    text = report.read_text(encoding="utf-8")
    for required in (
        "Actual production roster count",
        "Batch 005 import results",
        "Artwork review",
        "Expected roster count after publication",
        "Dataset integrity verification",
        "Exact owner-side approval and publication instructions",
    ):
        assert required in text
