"""Focused tests for cumulative Naruto balance verification."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path("data")


def load(name: str):
    return json.loads((ROOT / name).read_text(encoding="utf-8"))


def test_comparison_datasets_and_counts() -> None:
    comparison = load("naruto_cumulative_roster_comparison.json")
    datasets = comparison["datasets"]
    assert [datasets[k]["analysis"]["character_count"] for k in ("A", "B", "C")] == [53, 184, 236]
    assert all(not d["verified_published_snapshot"] for d in datasets.values())
    assert all(not d["duplicates_removed"] for d in datasets.values())
    assert comparison["snapshot_note"]
    ids_a = {c["character_id"] for c in datasets["A"]["characters"]}
    ids_b = {c["character_id"] for c in datasets["B"]["characters"]}
    ids_c = {c["character_id"] for c in datasets["C"]["characters"]}
    assert ids_a < ids_b < ids_c
    held = {c["character_id"] for c in load("naruto_batch_005_held_candidates.json")["candidates"]}
    assert not held & ids_c


def test_distribution_deltas_match_batch_005() -> None:
    comparison = load("naruto_cumulative_roster_comparison.json")
    b = comparison["datasets"]["B"]["analysis"]
    c = comparison["datasets"]["C"]["analysis"]
    assert c["character_count"] - b["character_count"] == 52
    assert c["rarity_distribution"]["Common"] - b["rarity_distribution"]["Common"] == 50
    assert c["power_distribution"]["1"] - b["power_distribution"]["1"] == 36
    assert c["healer_fit_counts"]["ge_3"] == b["healer_fit_counts"]["ge_3"]


def test_simulation_completeness_and_crosscheck() -> None:
    simulation = load("naruto_cumulative_balance_simulation.json")
    assert simulation["matches_per_dataset"] >= 20_000
    for label in ("A", "B", "C"):
        data = simulation["datasets"][label]
        assert data["matches_completed"] >= 20_000
        assert data["draft_completion_rate_pct"] == 100.0
        assert data["resolution_crosscheck"]["identical_pct"] == 100.0
        assert data["seeds"]["draw"] == 20261201
        assert data["seeds"]["role_assignment"] == 20261202
        assert data["winner_claim"] == "none"
        assert data["approval_claim"] == "none"


def test_integration_validation() -> None:
    validation = load("naruto_cumulative_integration_validation.json")
    checks = validation["checks"]
    assert checks["catalogue_imported"] == 62
    assert checks["importable_evaluation_count"] == 52
    assert checks["held_count"] == 10
    assert checks["held_candidates_kept_without_ratings"] is True
    assert checks["no_overlap_batch005_with_existing_datasets"] is True
    assert checks["audited_evaluations_unmodified"] is True
    assert "owner approval" in validation["recommendation"].lower()


def test_audited_package_preserved() -> None:
    changes = load("naruto_batch_005_rating_changes.json")
    held = load("naruto_batch_005_held_candidates.json")
    assert changes["change_count"] == len(changes["changes"]) == 7
    assert held["candidate_count"] == len(held["candidates"]) == 10


def test_report_exists() -> None:
    report = Path("docs") / "NARUTO_CUMULATIVE_BALANCE_REPORT.md"
    assert report.exists()
    text = report.read_text(encoding="utf-8")
    for required in (
        "Dataset construction",
        "Simulation methodology",
        "Batch 005 impact assessment",
        "Integration readiness",
        "Limitations",
    ):
        assert required in text
