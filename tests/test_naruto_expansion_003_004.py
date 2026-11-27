"""Validation tests for the consolidated Naruto expansion 003-004 deliverables."""

from __future__ import annotations

import json
from pathlib import Path

ROLES = {"captain", "strategist", "attacker", "tank", "assassin", "support", "healer"}
RARITIES = {"Common", "Uncommon", "Rare", "Epic", "Legendary"}


def load(name: str) -> dict:
    return json.loads((Path("data") / name).read_text(encoding="utf-8"))


def test_combined_evaluations_preserve_provenance() -> None:
    data = load("naruto_expansion_003_004_evaluations.json")
    assert data["counts"]["records"] == 149
    assert data["counts"]["draft"] == 132
    assert data["counts"]["held"] == 17
    for record in data["characters"]:
        assert "original" in record
        assert "revised" in record
        assert record["revised"]["name"] == record["name"]


def test_evaluated_dataset_counts_and_statuses() -> None:
    data = load("naruto_expansion_003_004_evaluated_dataset.json")
    assert data["record_count"] == 148
    assert data["draft_count"] == 131
    assert data["held_count"] == 17
    assert data["status"] == "draft"
    assert sum(data["rarity_distribution"].values()) == 131
    for record in data["characters"]:
        if record["held"]:
            assert record["evaluation_status"] == "held"
            continue
        assert record["evaluation_status"] == "draft"
        assert 1 <= record["power"] <= 5
        assert set(record["fit"]) == ROLES
        assert set(record["scores"]) == ROLES
        assert record["rarity"] in RARITIES
        assert record["scoring_version"] == "SCORE-1.0"
        assert record["rarity_detail"]["version"] == "RARITY-0.2"


def test_held_records_are_never_coerced_to_zero() -> None:
    data = load("naruto_expansion_003_004_evaluated_dataset.json")
    held = [r for r in data["characters"] if r["held"]]
    assert len(held) == 17
    for record in held:
        if record["power"] is None:
            assert record["fit"] is None
            assert record["scores"] is None
            assert record["rarity"] is None
        else:
            assert record["rarity_reference_only"] is True


def test_ka_import_separates_importable_and_held() -> None:
    data = load("naruto_expansion_003_004_ka_import.json")
    assert data["format_version"] == "KA-IMPORT-1.0"
    assert data["character_count"] == 131
    assert data["held_count"] == 17
    assert len(data["characters"]) == 131
    assert len(data["held_records"]) == 17
    for entry in data["characters"]:
        assert entry["importable"] is True
        assert entry["evaluation_status"] == "draft"
        assert entry["review_status"] == "pending"
        assert entry["rarity"] in RARITIES
        assert 1 <= entry["power"] <= 5
        assert set(entry["fit"]) == ROLES
    for entry in data["held_records"]:
        assert entry["importable"] is False
        assert entry["evaluation_status"] == "held"
        assert entry["rarity"] is None
        assert entry["power"] is None
        assert entry["fit"] is None


def test_image_manifest_has_full_coverage() -> None:
    data = load("naruto_expansion_003_004_image_manifest.json")
    assert data["summary"]["characters"] == 148
    assert data["summary"]["with_valid_image"] == 148
    assert data["summary"]["without_valid_image"] == 0
    assert data["summary"]["total_images"] == 181
    assert data["summary"]["valid_images"] == 180
    assert data["identity_verification"]["visual_identity_verified"] is False
    counts = data["identity_verification"]["counts"]
    assert counts["uncertain"] == 1
    assert counts["resolved_alias"] == 3
    assert counts["combined_record"] == 1
    assert counts["source_name_match"] == 143


def test_image_report_separates_accessibility_from_identity() -> None:
    data = load("naruto_expansion_003_004_image_report.json")
    assert data["summary"]["total_images"] == 181
    assert data["summary"]["valid_images"] == 180
    assert data["summary"]["missing_images"] == 1
    assert data["summary"]["duplicate_images"] == 0
    assert data["identity_verification"]["visual_identity_verified"] is False
    uncertain = data["identity_verification"]["uncertain_characters"]
    assert [record["name"] for record in uncertain] == ["White Zetsu"]
    assert len(data["non_valid_images"]) == 1
    assert data["non_valid_images"][0]["name"] == "Gamakichi"
    assert data["non_valid_images"][0]["status"] == "missing"


def test_balance_report_ran_ten_thousand_drafts_per_scenario() -> None:
    data = load("naruto_expansion_003_004_balance_report.json")
    assert data["simulation"]["drafts_per_scenario"] == 10_000
    for scenario in ("expansion_only", "combined"):
        result = data[scenario]
        assert result["drafts_requested"] == 10_000
        assert result["completed"] == 10_000
        assert result["failed"] == 0
        assert 0.45 <= result["first_player_win_rate_all_completed"] <= 0.55


def test_change_log_records_held_to_draft_conversions() -> None:
    data = load("naruto_expansion_003_004_change_log.json")
    assert data["change_count"] == len(data["changes"])
    status_changes = [c for c in data["changes"] if c["field"] == "evaluation_status"]
    assert len(status_changes) == 27
    conversions = [
        c
        for c in status_changes
        if c["previous"] == "held" and c["proposed"] == "draft" and c["batch"] in {"004-A", "004-B"}
    ]
    assert len(conversions) == 25


def test_no_expansion_record_is_approved_or_published() -> None:
    dataset = load("naruto_expansion_003_004_evaluated_dataset.json")
    assert dataset["status"] == "draft"
    for record in dataset["characters"]:
        assert record["evaluation_status"] in {"draft", "held"}
    ka_import = load("naruto_expansion_003_004_ka_import.json")
    for entry in ka_import["characters"] + ka_import["held_records"]:
        assert entry["review_status"] == "pending"
