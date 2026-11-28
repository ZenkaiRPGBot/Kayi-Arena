"""Structural, numerical, identity and artwork validation for the Batch 005 audit."""

from __future__ import annotations

import hashlib
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.scoring.engine import score_record
from app.scoring.models import SCORING_ROLES
from app.scoring.rarity_v02 import classify_rarity_v02

ROOT = Path("data")
ROLES = list(SCORING_ROLES)


def load(name: str) -> Any:
    return json.loads((ROOT / name).read_text(encoding="utf-8"))


def sha256(name: str) -> str:
    return hashlib.sha256((ROOT / name).read_bytes()).hexdigest()


def main() -> None:
    original = load("naruto_batch_005_claude_evaluation.json")
    details = load("naruto_batch_005_evaluation_details.json")
    advisory = load("naruto_batch_005_derived_role_scores_advisory.json")
    audited = load("naruto_batch_005_audited_evaluations.json")
    held = load("naruto_batch_005_held_candidates.json")
    audit_details = load("naruto_batch_005_audit_details.json")
    import_ready = load("naruto_batch_005_import_ready.json")
    changes = load("naruto_batch_005_rating_changes.json")
    research = load("naruto_batch_005_research.json")
    catalogue = load("naruto_batch_005_catalogue.json")
    manifest = load("naruto_batch_005_image_manifest.json")

    original_ids = [item["character_id"] for item in original["evaluations"]]
    research_ids = [item["candidate_id"] for item in research["candidates"]]
    assert original_ids == research_ids
    assert len(original_ids) == 62
    assert len(set(original_ids)) == 62

    importable = {item["character_id"] for item in audited["evaluations"]}
    held_ids = {item["character_id"] for item in held["candidates"]}
    assert importable | held_ids == set(original_ids)
    assert not importable & held_ids
    assert len(importable) == 52
    assert len(held_ids) == 10

    import_ready_ids = [item["character_id"] for item in import_ready["evaluations"]]
    assert set(import_ready_ids) == importable
    assert len(import_ready_ids) == len(set(import_ready_ids))

    assert import_ready["format_version"] == "KA-IMPORT-1.0"
    assert import_ready["batch_type"] == "evaluation"
    assert import_ready["universe_id"] == "naruto"
    assert import_ready["batch_id"] == "naruto-batch-005"
    assert import_ready["batch_status"] == "draft"

    for record in import_ready["evaluations"]:
        assert isinstance(record["power"], int) and 1 <= record["power"] <= 5
        assert list(record["fit"].keys()) == ROLES
        assert all(isinstance(value, int) and 0 <= value <= 5 for value in record["fit"].values())
        assert record["evidence"]
        assert record["source_references"]
        assert record["submit_for_review"] is True
        for forbidden in ("rarity", "role_score", "ecv_score", "matchups", "approved"):
            assert forbidden not in record

    detail_by_id = {item["character_id"]: item for item in audit_details["candidates"]}
    assert set(detail_by_id) == set(original_ids)
    advisory_matches_original = 0
    advisory_matches_audited = 0
    for cid, detail in detail_by_id.items():
        assert detail["original"]["power"] == next(
            e["power"] for e in original["evaluations"] if e["character_id"] == cid
        )
        assert detail["audited"]["power"] == detail["audited"]["power"]
        scores = dict(
            score_record(
                {
                    "character_id": cid,
                    "power": detail["audited"]["power"],
                    "fit": detail["audited"]["fit"],
                }
            ).scores
        )
        assert scores == detail["audited"]["scores"]
        rarity = classify_rarity_v02(
            power=detail["audited"]["power"],
            role_fits=detail["audited"]["fit"],
            role_scores=scores,
            apply_naruto_healer_floor=True,
        )
        assert rarity.final_rarity == detail["audited"]["rarity"]["final_rarity"]
        adv = advisory["scores"][cid]
        original_scores = detail["original"]["scores"]
        if all(adv[role] == original_scores[role] for role in ROLES):
            advisory_matches_original += 1
        if all(adv[role] == scores[role] for role in ROLES):
            advisory_matches_audited += 1
        if cid in importable:
            assert detail["artwork"]["technical_valid"] is True
            assert detail["artwork"]["catalogue_present"] is True

    assert advisory_matches_original == audit_details["advisory_score_check"]["advisory_matches_original_ratings"] == 62
    assert advisory_matches_audited == audit_details["advisory_score_check"]["advisory_matches_audited_ratings"] == 58

    for item in held["candidates"]:
        assert item["importable"] is False
        assert item["power"] is None
        assert item["fit"] is None
        assert item["reason"]

    assert changes["change_count"] == len(changes["changes"]) == 7
    assert len(details["evaluation_details"]) == 62

    catalogue_ids = {item["candidate_id"] for item in catalogue["candidates"]}
    valid_art_ids = {
        item["candidate_id"] for item in manifest["images"] if item["status"] == "valid"
    }
    assert importable <= catalogue_ids
    assert importable <= valid_art_ids

    print(
        json.dumps(
            {
                "original_records": len(original_ids),
                "importable": len(importable),
                "held": len(held_ids),
                "rating_changes": len(changes["changes"]),
                "advisory_matches_original": advisory_matches_original,
                "advisory_matches_audited": advisory_matches_audited,
                "original_hashes": {
                    "claude_evaluation": sha256("naruto_batch_005_claude_evaluation.json"),
                    "evaluation_details": sha256("naruto_batch_005_evaluation_details.json"),
                    "advisory": sha256("naruto_batch_005_derived_role_scores_advisory.json"),
                    "passA": sha256("naruto_batch_005_passA_fit_frozen.py"),
                },
                "power_distribution": dict(
                    sorted(Counter(item["power"] for item in import_ready["evaluations"]).items())
                ),
                "status": "validated",
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
