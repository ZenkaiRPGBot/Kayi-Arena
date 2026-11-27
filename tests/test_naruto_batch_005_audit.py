"""Focused tests for the independent Naruto Batch 005 audit."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.scoring.engine import score_record
from app.scoring.models import SCORING_ROLES
from app.scoring.rarity_v02 import classify_rarity_v02

ROOT = Path("data")
ROLES = list(SCORING_ROLES)


def load(name: str):
    return json.loads((ROOT / name).read_text(encoding="utf-8"))


def test_original_claude_outputs_are_preserved() -> None:
    for name in (
        "naruto_batch_005_claude_evaluation.json",
        "naruto_batch_005_evaluation_details.json",
        "naruto_batch_005_final_report.md",
        "naruto_batch_005_derived_role_scores_advisory.json",
        "naruto_batch_005_build_and_validate.py",
        "naruto_batch_005_passA_fit_frozen.py",
    ):
        assert (ROOT / name).exists()
        assert (ROOT / name).stat().st_size > 100
    assert len(load("naruto_batch_005_claude_evaluation.json")["evaluations"]) == 62
    assert len(load("naruto_batch_005_evaluation_details.json")["evaluation_details"]) == 62


def test_all_62_candidates_are_accounted_for() -> None:
    audited = load("naruto_batch_005_audited_evaluations.json")
    held = load("naruto_batch_005_held_candidates.json")
    details = load("naruto_batch_005_audit_details.json")
    importable_ids = {item["character_id"] for item in audited["evaluations"]}
    held_ids = {item["character_id"] for item in held["candidates"]}
    assert len(importable_ids) == 52
    assert len(held_ids) == 10
    assert importable_ids | held_ids == {item["character_id"] for item in details["candidates"]}
    assert not importable_ids & held_ids
    assert details["candidate_count"] == 62


def test_held_candidates_have_no_ratings_and_reasons() -> None:
    held = load("naruto_batch_005_held_candidates.json")
    for item in held["candidates"]:
        assert item["importable"] is False
        assert item["power"] is None
        assert item["fit"] is None
        assert item["reason"]
        assert item["hold_code"]


def test_import_ready_matches_schema_and_audited_ratings() -> None:
    import_ready = load("naruto_batch_005_import_ready.json")
    audited = load("naruto_batch_005_audited_evaluations.json")
    assert import_ready["format_version"] == "KA-IMPORT-1.0"
    assert import_ready["batch_type"] == "evaluation"
    assert import_ready["batch_status"] == "draft"
    expected = {item["character_id"]: item for item in audited["evaluations"]}
    for item in import_ready["evaluations"]:
        source = expected[item["character_id"]]
        assert item["power"] == source["power"]
        assert item["fit"] == source["fit"]
        assert list(item["fit"].keys()) == ROLES
        assert all(isinstance(v, int) and 0 <= v <= 5 for v in item["fit"].values())
        assert item["evidence"]
        assert item["source_references"]
        assert item["submit_for_review"] is True
        for forbidden in ("rarity", "role_score", "ecv_score", "matchups", "approved"):
            assert forbidden not in item


def test_authoritative_scores_and_rarity_recompute() -> None:
    details = load("naruto_batch_005_audit_details.json")
    for item in details["candidates"]:
        scores = dict(
            score_record(
                {
                    "character_id": item["character_id"],
                    "power": item["audited"]["power"],
                    "fit": item["audited"]["fit"],
                }
            ).scores
        )
        assert scores == item["audited"]["scores"]
        rarity = classify_rarity_v02(
            power=item["audited"]["power"],
            role_fits=item["audited"]["fit"],
            role_scores=scores,
            apply_naruto_healer_floor=True,
        )
        assert rarity.final_rarity == item["audited"]["rarity"]["final_rarity"]


def test_advisory_matches_original_but_not_all_audited() -> None:
    details = load("naruto_batch_005_audit_details.json")
    advisory = load("naruto_batch_005_derived_role_scores_advisory.json")["scores"]
    original_matches = 0
    audited_matches = 0
    for item in details["candidates"]:
        adv = advisory[item["character_id"]]
        if all(adv[role] == item["original"]["scores"][role] for role in ROLES):
            original_matches += 1
        if all(adv[role] == item["audited"]["scores"][role] for role in ROLES):
            audited_matches += 1
    assert original_matches == 62
    assert audited_matches == 58


def test_rating_changes_are_documented() -> None:
    changes = load("naruto_batch_005_rating_changes.json")
    assert changes["change_count"] == len(changes["changes"]) == 7
    for item in changes["changes"]:
        for key in (
            "character_id",
            "name",
            "field",
            "original_rating",
            "revised_rating",
            "supporting_evidence",
            "calibration_justification",
            "confidence",
            "reason",
        ):
            assert key in item


def test_importable_artwork_is_technically_valid() -> None:
    details = load("naruto_batch_005_audit_details.json")
    for item in details["candidates"]:
        if item["audit_status"] == "importable":
            assert item["artwork"]["technical_valid"] is True
            assert item["artwork"]["catalogue_present"] is True
            assert item["artwork"]["publication_permission"].startswith("source-dependent")
            assert item["artwork"]["visual_identity_verified"] is False


@pytest.mark.parametrize(
    "name",
    [
        "naruto_batch_005_audited_evaluations.json",
        "naruto_batch_005_held_candidates.json",
        "naruto_batch_005_audit_details.json",
        "naruto_batch_005_import_ready.json",
        "naruto_batch_005_rating_changes.json",
        "NARUTO_BATCH_005_INDEPENDENT_AUDIT_REPORT.md",
        "naruto_batch_005_audit_simulation.json",
    ],
)
def test_deliverables_exist(name: str) -> None:
    assert (ROOT / name).exists() if name.startswith("naruto_") else (Path("docs") / name).exists()
    target = ROOT / name if name.startswith("naruto_") else Path("docs") / name
    assert target.stat().st_size > 100
