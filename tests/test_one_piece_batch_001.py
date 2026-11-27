"""Focused quality tests for One Piece Batch 001 research preparation."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.one_piece_quality import (  # noqa: E402
    build_completeness_report,
    is_placeholder,
    is_substantive_ability,
    is_substantive_text,
    research_ready_valid,
)

ROOT = Path("data")


def load(name: str):
    return json.loads((ROOT / name).read_text(encoding="utf-8"))


def test_placeholders_and_metadata_are_not_substantive() -> None:
    for value in ("", "unknown", "n/a", "none recorded", None, []):
        assert is_placeholder(value)
        assert not is_substantive_text(value)
    assert is_placeholder("Rank: Admiral; affiliation: Marines")
    assert not is_substantive_text("Debut: One Piece chapter 550.")
    assert is_substantive_text("Used Armament Haki to deflect a lethal strike.")


def test_metadata_only_record_cannot_be_research_ready() -> None:
    record = {
        "status": "RESEARCH_READY",
        "demonstrated_abilities": [],
        "supporting_evidence": [
            {
                "url": "https://onepiece.fandom.com/wiki/Example",
                "verification_level": "inspected_secondary",
            }
        ],
        "capability_summary": {
            "offense": "Rank: Admiral.",
            "defense": "not recorded",
        },
    }
    valid, errors = research_ready_valid(record)
    assert not valid
    assert "no substantive demonstrated ability" in errors
    assert "fewer than two substantive capability-summary fields" in errors


def test_substantive_record_with_traceable_evidence_is_research_ready() -> None:
    record = {
        "status": "RESEARCH_READY",
        "demonstrated_abilities": [
            {
                "name": "Armament Haki",
                "description": (
                    "Hardened his arms with Armament Haki and blocked a slash that "
                    "had cut through steel, then countered with a Haki-infused "
                    "strike that broke the enemy's guard during the same exchange."
                ),
                "categories": ["offense", "defense_durability"],
                "canonical_refs": ["One Piece chapter 668"],
            },
            {
                "name": "Speed and Agility",
                "description": (
                    "Moved between three attackers before any of them could react "
                    "and cut them down in a single pass, then unsheathed and "
                    "resheathed his sword before the onlookers registered the strike."
                ),
                "categories": ["speed_mobility"],
                "canonical_refs": ["One Piece chapter 195"],
            },
        ],
        "supporting_evidence": [
            {
                "url": "https://onepiece.fandom.com/wiki/Roronoa_Zoro/Abilities_and_Powers",
                "verification_level": "inspected_secondary",
            }
        ],
        "capability_summary": {
            "offense": "Uses Haki-infused swordsmanship.",
            "speed_mobility": "Demonstrated rapid movement and reactions.",
        },
    }
    assert all(is_substantive_ability(item) for item in record["demonstrated_abilities"])
    assert research_ready_valid(record)[0] is True


def test_completion_stages_remain_separate() -> None:
    catalogue = {
        "stats": {"targets": 1},
        "candidates": [{"candidate_id": "one_piece_test", "name": "Test"}],
    }
    manifest = {
        "summary": {
            "candidates_with_valid_artwork": 1,
            "valid": 1,
            "total_images": 1,
        }
    }
    research = {
        "batch_id": "one-piece-test",
        "candidates": [
            {
                "candidate_id": "one_piece_test",
                "name": "Test",
                "research_gate": "INSUFFICIENT_EVIDENCE",
                "capability_summary": {},
                "demonstrated_abilities": [],
                "supporting_evidence": [],
            }
        ],
    }
    report = build_completeness_report(catalogue, manifest, research, None)
    stages = report["stages"]
    assert stages["catalogue"]["complete"] is True
    assert stages["artwork"]["complete"] is True
    assert stages["research"]["classification_complete"] is True
    assert stages["research"]["complete"] is False
    assert stages["evaluation"]["complete"] is False
    assert stages["publication"]["ready"] is False


def test_batch_001_gate_is_strict_and_consistent() -> None:
    research = load("one_piece_batch_001_research.json")
    catalogue = load("one_piece_batch_001_catalogue.json")
    unresolved = load("one_piece_batch_001_unresolved_candidates.json")
    manifest = load("one_piece_batch_001_image_manifest.json")
    completeness = load("one_piece_batch_001_completeness_report.json")

    research_ids = {item["candidate_id"] for item in research["candidates"]}
    catalogue_ids = {item["candidate_id"] for item in catalogue["candidates"]}
    unresolved_ids = {item["candidate_id"] for item in unresolved["candidates"]}
    assert research_ids == catalogue_ids
    assert not research_ids & unresolved_ids
    assert len(research_ids) == len(research["candidates"]) >= 60

    for record in research["candidates"]:
        assert record["research_gate"] == "RESEARCH_READY"
        assert record["demonstrated_abilities"]
        assert record["supporting_evidence"]
        assert research_ready_valid(record)[0] is True
        assert record["canonical_policy"] == "ONE-PIECE-CANON-0.1"
        assert record["manga_cutoff_chapter"] == 1100
        for key in ("power", "fit", "rarity", "role_score", "approved", "approval"):
            assert key not in record

    valid_artwork_ids = {
        item["candidate_id"]
        for item in manifest["images"]
        if item["status"] == "valid" and item["in_catalogue"]
    }
    assert research_ids <= valid_artwork_ids
    assert completeness["stages"]["research"]["complete"] is True
    assert completeness["stages"]["publication"]["ready"] is False


def test_unresolved_candidates_preserve_rejection_reasons() -> None:
    unresolved = load("one_piece_batch_001_unresolved_candidates.json")
    assert unresolved["excluded_from_evaluation_package"] is True
    assert unresolved["candidate_count"] == len(unresolved["candidates"])
    for item in unresolved["candidates"]:
        assert item["research_gate"] in {"PARTIAL_RESEARCH", "INSUFFICIENT_EVIDENCE"}
        assert item["reason"]
        assert item["preserved_for_future_research"] is True


def test_master_registry_and_progress_are_cumulative_ready() -> None:
    registry = load("one_piece_master_registry.json")
    progress = load("one_piece_expansion_progress.json")
    assert registry["universe_id"] == "one_piece"
    assert "one-piece-batch-001" in registry["batches"]
    assert all(
        item["evaluation_status"] == "not_started"
        and item["approval_status"] == "not_approved"
        for item in registry["characters"]
    )
    assert progress["batches_completed"] >= 1
    assert progress["totals"]["research_ready"] >= len(
        load("one_piece_batch_001_research.json")["candidates"]
    )
    assert progress["totals"]["approved"] == 0
    assert progress["totals"]["published"] == 0


def test_assignment_is_self_contained() -> None:
    assignment = (
        ROOT / "one_piece_batch_001_claude_assignment.md"
    ).read_text(encoding="utf-8")
    for required in (
        "ONE-PIECE-CANON-0.1",
        "Manga cutoff: Chapter 1100",
        "EVAL-FRAMEWORK-1.0",
        '"captain"',
        '"strategist"',
        '"attacker"',
        '"tank"',
        '"assassin"',
        '"support"',
        '"healer"',
        '"evaluation_status"',
        "one_piece_batch_001_research.json",
        "Ready-to-use prompt",
        "Do not approve, publish or calculate rarity",
    ):
        assert required in assignment


@pytest.mark.parametrize(
    "name",
    [
        "one_piece_batch_001_catalogue.json",
        "one_piece_batch_001_research.json",
        "one_piece_batch_001_image_manifest.json",
        "one_piece_batch_001_claude_assignment.md",
        "one_piece_batch_001_unresolved_candidates.json",
        "one_piece_batch_001_completeness_report.json",
    ],
)
def test_required_deliverables_exist(name: str) -> None:
    assert (ROOT / name).exists()
    assert (ROOT / name).stat().st_size > 100
