"""Focused quality-gate tests for Naruto Batch 005 corrective research."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.batch_005_quality import (
    assess_evaluation,
    assess_research,
    build_report,
    is_placeholder,
    is_substantive_ability,
    is_substantive_text,
    research_ready_valid,
)


def load(name: str):
    return json.loads((Path("data") / name).read_text(encoding="utf-8"))


def test_placeholders_and_metadata_do_not_count_as_substantive() -> None:
    for value in ("", "not recorded", "none recorded", "unknown", "n/a", None, []):
        assert is_placeholder(value)
        assert not is_substantive_text(value)
    assert is_placeholder("Rank: Part II: Jōnin; affiliation: Konohagakure")
    assert not is_substantive_text("Debut: Naruto Chapter #542.")
    assert is_substantive_text("Used Shadow Imitation Technique to restrain the Ten-Tails.")


def test_metadata_only_record_cannot_be_research_ready() -> None:
    record = {
        "status": "RESEARCH_READY",
        "demonstrated_abilities": [],
        "supporting_evidence": [
            {
                "url": "https://naruto.fandom.com/wiki/Example",
                "verification_level": "inspected_secondary",
            }
        ],
        "capability_summary": {"offense": "Rank: Jōnin.", "defense": "not recorded"},
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
                "name": "Shadow Imitation Technique",
                "description": "Restrained the Ten-Tails' shadow with other Nara clan members.",
                "categories": ["support", "battlefield_control"],
                "canonical_refs": ["Naruto chapter 639"],
            }
        ],
        "supporting_evidence": [
            {
                "url": "https://naruto.fandom.com/wiki/Daen_Nara",
                "verification_level": "inspected_secondary",
                "canonical_refs": ["Naruto chapter 639"],
            }
        ],
        "capability_summary": {
            "offense": "Used telekinetic blade control to attack from multiple angles.",
            "support_control": "Joined a clan-wide shadow restraint against the Ten-Tails.",
        },
    }
    assert is_substantive_ability(record["demonstrated_abilities"][0])
    assert research_ready_valid(record)[0] is True


def test_report_keeps_five_completion_concepts_separate() -> None:
    catalogue = {
        "stats": {"targets": 1},
        "candidates": [{"candidate_id": "dattebayo:1", "name": "A"}],
    }
    manifest = {
        "summary": {
            "candidates_with_valid_artwork": 1,
            "total_images": 1,
            "valid": 1,
        }
    }
    research = {
        "candidates": [
            {
                "candidate_id": "dattebayo:1",
                "name": "A",
                "research_gate": "INSUFFICIENT_EVIDENCE",
                "capability_summary": {},
                "demonstrated_abilities": [],
                "supporting_evidence": [],
            }
        ]
    }
    report = build_report(catalogue, manifest, research, None)
    stages = report["stages"]
    assert stages["catalogue"]["complete"] is True
    assert stages["artwork"]["complete"] is True
    assert stages["research"]["status_counts"]["INSUFFICIENT_EVIDENCE"] == 1
    assert stages["research"]["classification_complete"] is True
    assert stages["research"]["complete"] is False
    assert stages["evaluation"]["complete"] is False
    assert stages["publication"]["ready"] is False
    assert report["policy"]["catalogue_and_artwork_do_not_imply_research_quality"] is True


def test_original_placeholder_evaluation_is_not_complete() -> None:
    evaluation = load("naruto_batch_005_original_claude_evaluation.json")
    assessment = assess_evaluation(evaluation)
    assert assessment["evaluations"] == 100
    assert assessment["draft"] == 1
    assert assessment["held"] == 99
    assert assessment["placeholder_power_floor"] is True
    assert assessment["complete"] is False


def test_original_metadata_only_research_is_not_complete() -> None:
    research = load("naruto_batch_005_original_research.json")
    assessment = assess_research(research)
    assert assessment["total_records"] == 100
    assert assessment["status_counts"]["RESEARCH_READY"] == 0
    assert assessment["complete"] is False


def test_revised_package_enforces_research_quality_gate() -> None:
    research = load("naruto_batch_005_research.json")
    catalogue = load("naruto_batch_005_catalogue.json")
    unresolved = load("naruto_batch_005_unresolved_candidates.json")

    research_ids = {item["candidate_id"] for item in research["candidates"]}
    catalogue_ids = {item["candidate_id"] for item in catalogue["candidates"]}
    assert research_ids == catalogue_ids
    assert len(research_ids) == len(research["candidates"]) == len(catalogue["candidates"])

    assessment = assess_research(research, catalogue)
    assert assessment["complete"] is True
    assert assessment["status_counts"]["RESEARCH_READY"] == len(research["candidates"])
    assert assessment["invalid_research_ready_records"] == []

    for record in research["candidates"]:
        assert record["research_gate"] == "RESEARCH_READY"
        assert record["demonstrated_abilities"]
        assert record["supporting_evidence"]
        assert research_ready_valid(record)[0] is True
        for key in ("power", "fit", "rarity", "role_score", "approved"):
            assert key not in record

    unresolved_ids = {item["candidate_id"] for item in unresolved["candidates"]}
    assert not unresolved_ids & research_ids
    assert unresolved["excluded_from_evaluation_package"] is True
