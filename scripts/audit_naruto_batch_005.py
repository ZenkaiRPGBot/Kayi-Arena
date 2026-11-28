"""Independent audit of Claude's Naruto Batch 005 evaluations.

Stage: audit and integration preparation only. No character is approved,
published or imported into a playable dataset. Original Claude outputs are
preserved unchanged; all derived files are written to data/.
"""

from __future__ import annotations

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
DATE = "2026-11-27"

ROLES = list(SCORING_ROLES)
FIT_ORDER = ["captain", "strategist", "attacker", "tank", "assassin", "support", "healer"]

HELD = {
    "dattebayo:901": (
        "BORUTO_ERA_ELIGIBILITY_UNRESOLVED",
        "Boruto-era sensor with no verified Naruto-era version in the supplied package. "
        "The authoritative Naruto universe policy does not independently expand to "
        "Boruto-exclusive characters; owner decision required.",
    ),
    "dattebayo:1413": (
        "BORUTO_ERA_ELIGIBILITY_UNRESOLVED",
        "Boruto-era anime evidence with no verified Naruto-era ability baseline; hold for owner review.",
    ),
    "dattebayo:846": (
        "BORUTO_ERA_ELIGIBILITY_UNRESOLVED",
        "Boruto-era candidate with adaptation-sensitive evidence and disputed era eligibility.",
    ),
    "dattebayo:1068": (
        "BORUTO_ERA_ELIGIBILITY_UNRESOLVED",
        "Boruto-era Senka brother; era eligibility unresolved under NARUTO-CANON-0.1.",
    ),
    "dattebayo:1069": (
        "BORUTO_ERA_ELIGIBILITY_UNRESOLVED",
        "Boruto-era Senka brother; era eligibility unresolved under NARUTO-CANON-0.1.",
    ),
    "dattebayo:1070": (
        "BORUTO_ERA_ELIGIBILITY_UNRESOLVED",
        "Boruto-era Senka brother; era eligibility unresolved under NARUTO-CANON-0.1.",
    ),
    "dattebayo:1377": (
        "BORUTO_ERA_ELIGIBILITY_UNRESOLVED",
        "Boruto-era hearing/support specialist; era eligibility unresolved under NARUTO-CANON-0.1.",
    ),
    "dattebayo:435": (
        "BORUTO_ERA_ELIGIBILITY_UNRESOLVED",
        "Hanabi's supplied combat evidence is adaptation/Boruto-era material; no verified "
        "Naruto-era combat baseline. Hold rather than silently expanding the Naruto universe boundary.",
    ),
    "dattebayo:434": (
        "INSUFFICIENT_DEMONSTRATED_ABILITY",
        "Only anime-only, implied taijutsu and a long leap are supplied; the source explicitly "
        "says the extent of his abilities is unknown. No defensible numerical evaluation can be established.",
    ),
    "dattebayo:801": (
        "BORROWED_EQUIPMENT_ONLY",
        "The only demonstrated action uses Minato's Flying Thunder God kunai; sword skill is "
        "merely implied and no personal technique or result is supplied. Borrowed equipment "
        "is excluded under NARUTO-CANON-0.1.",
    ),
}

# (field, revised value, evidence, calibration, confidence, reason)
CHANGES: dict[str, list[tuple[str, int, str, str, str, str]]] = {
    "dattebayo:948": [
        (
            "healer",
            0,
            "Supplied evidence is medical analysis of Pain's Animal Path; the page infers "
            "knowledge and chakra control but shows no treatment of a patient.",
            "Karin (Healer 3) and Shizune (Healer 4) are treatment anchors; analysis alone "
            "does not meet Healer 1.",
            "low",
            "An inferred medical role is not a demonstrated ability to treat others.",
        )
    ],
    "dattebayo:706": [
        (
            "healer",
            0,
            "Supplied evidence is medical analysis of Pain's Animal Path with no treatment "
            "technique or combat feat shown.",
            "Karin (Healer 3) and Shizune (Healer 4) require actual healing actions; "
            "inference-only medical knowledge does not qualify.",
            "low",
            "Remove an inferred Healer Fit that lacks a demonstrated treatment action.",
        )
    ],
    "dattebayo:810": [
        (
            "healer",
            0,
            "Manga-supplied evidence shows medical diagnosis only. First-aid deployment and "
            "memory-restoration genjutsu are anime-only and excluded by NARUTO-CANON-0.1.",
            "Healer Fit requires demonstrated treatment of others, not diagnosis alone; "
            "Shizune and Sakura are treatment anchors.",
            "medium",
            "Apply the canonical policy to anime-only healing evidence.",
        )
    ],
    "dattebayo:1337": [
        (
            "power",
            1,
            "The only manga-supported capability is basic medical assistance. Kenjutsu "
            "competence is explicitly unknown in the manga; other material is anime-only.",
            "Zaji (Power 1 support specialist) and non-combatant anchors support Power 1 "
            "for a support-only character with no demonstrated combat effectiveness.",
            "low",
            "Power 2 was the adaptation ceiling, not demonstrated combat capability.",
        ),
        (
            "attacker",
            0,
            "No manga-demonstrated offensive technique or result is supplied.",
            "Attacker Fit requires direct offensive effectiveness; comparison with Hinata "
            "and Ino anchors keeps zero where offense is not demonstrated.",
            "low",
            "Anime-only kenjutsu expansion cannot support Attacker Fit under the policy.",
        ),
        (
            "assassin",
            0,
            "No demonstrated stealth, infiltration or precision elimination is supplied.",
            "Kakashi and Torune anchors require concrete stealth or infiltration actions.",
            "low",
            "Remove unsupported Assassin Fit.",
        ),
        (
            "strategist",
            0,
            "No demonstrated planning or tactical decision is supplied.",
            "Shikamaru/Shikaku anchors require demonstrated tactical action.",
            "low",
            "Remove unsupported Strategist Fit.",
        ),
    ],
}

CHANGE_NOTE = {
    "dattebayo:948": "Healer Fit removed; all other ratings retained.",
    "dattebayo:706": "Healer Fit removed; all other ratings retained.",
    "dattebayo:810": "Healer Fit removed after anime-only exclusion.",
    "dattebayo:1337": "Power and three unsupported role Fits lowered; Support 1 and Healer 1 retained.",
}


def load(name: str) -> Any:
    return json.loads((ROOT / name).read_text(encoding="utf-8"))


def write(name: str, payload: Any) -> None:
    (ROOT / name).write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def compute_scores_and_rarity(power: int, fit: dict[str, int]) -> tuple[dict[str, int], dict[str, Any]]:
    output = score_record({"character_id": "_audit", "power": power, "fit": fit})
    scores = dict(output.scores)
    rarity = classify_rarity_v02(
        power=power,
        role_fits=fit,
        role_scores=scores,
        apply_naruto_healer_floor=True,
    )
    return scores, {
        "version": rarity.version,
        "rarity_points": rarity.rarity_points,
        "base_rarity": rarity.base_rarity,
        "final_rarity": rarity.final_rarity,
        "highest_role_score": rarity.highest_role_score,
        "combat_bonus": rarity.combat_bonus,
        "specialist_bonus": rarity.specialist_bonus,
        "versatility_bonus": rarity.versatility_bonus,
        "floor_applied": rarity.floor_applied,
    }


def main() -> None:
    claude = load("naruto_batch_005_claude_evaluation.json")
    details = load("naruto_batch_005_evaluation_details.json")["evaluation_details"]
    research = load("naruto_batch_005_research.json")["candidates"]
    advisory = load("naruto_batch_005_derived_role_scores_advisory.json")
    catalogue = load("naruto_batch_005_catalogue.json")
    manifest = load("naruto_batch_005_image_manifest.json")

    name_by_id = {item["candidate_id"]: item["name"] for item in research}
    research_by_id = {item["candidate_id"]: item for item in research}
    image_by_id = {item["candidate_id"]: item for item in manifest["images"]}
    catalogue_by_id = {item["candidate_id"]: item for item in catalogue["candidates"]}

    audited: list[dict[str, Any]] = []
    held: list[dict[str, Any]] = []
    audit_details: list[dict[str, Any]] = []
    change_log: list[dict[str, Any]] = []
    advisory_matches_original = 0
    advisory_matches_audited = 0

    for original in claude["evaluations"]:
        cid = original["character_id"]
        original_power = original["power"]
        original_fit = dict(original["fit"])
        revised_power = original_power
        revised_fit = dict(original_fit)
        changes: list[dict[str, Any]] = []

        for field, value, evidence, calibration, confidence, reason in CHANGES.get(cid, []):
            before = revised_power if field == "power" else revised_fit[field]
            if field == "power":
                revised_power = value
            else:
                revised_fit[field] = value
            change = {
                "character_id": cid,
                "name": name_by_id.get(cid, cid),
                "field": field,
                "original_rating": before,
                "revised_rating": value,
                "supporting_evidence": evidence,
                "calibration_justification": calibration,
                "confidence": confidence,
                "reason": reason,
            }
            changes.append(change)
            change_log.append(change)

        status = "held" if cid in HELD else "importable"
        hold_code, hold_reason = HELD.get(cid, ("", ""))
        scores, rarity = compute_scores_and_rarity(revised_power, revised_fit)
        original_scores, original_rarity = compute_scores_and_rarity(original_power, original_fit)
        adv = advisory["scores"].get(cid, {})
        if all(adv.get(role) == original_scores[role] for role in ROLES):
            advisory_matches_original += 1
        if all(adv.get(role) == scores[role] for role in ROLES):
            advisory_matches_audited += 1

        image = image_by_id.get(cid, {})
        artwork = {
            "technical_valid": image.get("status") == "valid",
            "image_status": image.get("status"),
            "image_url": image.get("image_url"),
            "catalogue_present": cid in catalogue_by_id,
            "visual_identity_verified": False,
            "canonical_version_verified": False,
            "publication_permission": "source-dependent; review required",
            "unresolved_issue": (
                None
                if image.get("status") == "valid" and cid in catalogue_by_id
                else "Artwork or catalogue association missing for this candidate."
            ),
        }

        detail = details.get(cid, {})
        detail_flags = list(detail.get("review_flags") or [])
        if status == "held":
            detail_flags = sorted(set(detail_flags + ["AUDIT_HELD", hold_code]))
        elif changes:
            detail_flags = sorted(set(detail_flags + ["AUDIT_RATING_REVISED"]))
        else:
            detail_flags = sorted(set(detail_flags + ["AUDIT_RATING_RETAINED"]))

        audit_details.append(
            {
                "character_id": cid,
                "name": name_by_id.get(cid, cid),
                "research_gate": research_by_id.get(cid, {}).get("research_gate"),
                "audit_status": status,
                "original": {
                    "power": original_power,
                    "fit": original_fit,
                    "scores": original_scores,
                    "rarity": original_rarity,
                },
                "audited": {
                    "power": revised_power,
                    "fit": revised_fit,
                    "scores": scores,
                    "rarity": rarity,
                },
                "changes": changes,
                "audit_decision": (
                    CHANGE_NOTE.get(cid, "All Claude ratings retained after independent review.")
                    if status != "held" and changes
                    else (
                        "All Claude ratings retained after independent review."
                        if status != "held"
                        else "Excluded from importable evaluation package pending owner review."
                    )
                ),
                "hold_reason": hold_reason or None,
                "missing_evidence": (
                    detail.get("contradictions_or_outliers") if status == "held" else None
                ),
                "confidence": detail.get("confidence", {}).get("power", "low"),
                "review_flags": detail_flags,
                "evidence": original["evidence"],
                "source_references": original["source_references"],
                "revision_ref": original["revision_ref"],
                "artwork": artwork,
            }
        )

        if status == "held":
            held.append(
                {
                    "character_id": cid,
                    "name": name_by_id.get(cid, cid),
                    "importable": False,
                    "power": None,
                    "fit": None,
                    "hold_code": hold_code,
                    "reason": hold_reason,
                    "source_references": original["source_references"],
                    "review_flags": detail_flags,
                }
            )
            continue

        audited.append(
            {
                "character_id": cid,
                "name": name_by_id.get(cid, cid),
                "power": revised_power,
                "fit": revised_fit,
                "scores": scores,
                "rarity": rarity,
                "evidence": original["evidence"],
                "source_references": original["source_references"],
                "revision_ref": original["revision_ref"],
                "submit_for_review": True,
                "audit_status": "importable",
                "audit_changes": changes,
            }
        )

    importable_ids = {item["character_id"] for item in audited}
    held_ids = {item["character_id"] for item in held}
    assert not importable_ids & held_ids
    assert len(importable_ids) + len(held_ids) == 62
    assert all(item["artwork"]["technical_valid"] for item in audit_details if item["audit_status"] == "importable")

    write(
        "naruto_batch_005_audited_evaluations.json",
        {
            "universe_id": "naruto",
            "batch_id": "naruto-batch-005",
            "audit_version": "NARUTO-BATCH-005-AUDIT-0.1",
            "prepared_date": DATE,
            "canonical_policy": "NARUTO-CANON-0.1",
            "scoring_version": "SCORE-1.0",
            "rarity_version": "RARITY-0.2",
            "status": "draft_audit_preparation",
            "original_claude_file": "naruto_batch_005_claude_evaluation.json",
            "counts": {
                "candidates_accounted": 62,
                "importable": len(audited),
                "held": len(held),
                "ratings_changed": len(change_log),
            },
            "evaluations": audited,
        },
    )

    write(
        "naruto_batch_005_held_candidates.json",
        {
            "universe_id": "naruto",
            "batch_id": "naruto-batch-005",
            "generated_at": DATE,
            "excluded_from_import": True,
            "candidate_count": len(held),
            "candidates": held,
        },
    )

    write(
        "naruto_batch_005_audit_details.json",
        {
            "universe_id": "naruto",
            "batch_id": "naruto-batch-005",
            "generated_at": DATE,
            "candidate_count": len(audit_details),
            "advisory_score_check": {
                "advisory_matches_original_ratings": advisory_matches_original,
                "advisory_matches_audited_ratings": advisory_matches_audited,
                "note": "Advisory scores were computed from Claude's original ratings. Differences after audit are expected where ratings changed.",
            },
            "candidates": audit_details,
        },
    )

    write(
        "naruto_batch_005_rating_changes.json",
        {
            "batch_id": "naruto-batch-005",
            "generated_at": DATE,
            "change_count": len(change_log),
            "changes": change_log,
        },
    )

    import_ready = {
        "format_version": "KA-IMPORT-1.0",
        "batch_type": "evaluation",
        "universe_id": "naruto",
        "batch_id": "naruto-batch-005",
        "evaluation_framework_version": "EVAL-FRAMEWORK-1.0",
        "scoring_version": "SCORE-1.0",
        "canonical_policy_version": "NARUTO-CANON-0.1",
        "batch_status": "draft",
        "global_notes": [
            "Independent audit of Claude's 62 Draft evaluations; 10 records held and excluded.",
            "No Power or Role Fit was invented to satisfy an import schema.",
            "Authoritative SCORE-1.0 and RARITY-0.2 calculations are recorded in the audit details companion file.",
            "No character is approved, published or imported into a playable dataset.",
        ],
        "evaluations": [
            {
                "character_id": item["character_id"],
                "power": item["power"],
                "fit": item["fit"],
                "evidence": item["evidence"],
                "source_references": item["source_references"],
                "revision_ref": item["revision_ref"] + "-audit",
                "submit_for_review": True,
            }
            for item in audited
        ],
    }
    write("naruto_batch_005_import_ready.json", import_ready)

    power_counts = Counter(item["power"] for item in audited)
    original_power_counts = Counter(e["power"] for e in claude["evaluations"])
    rarity_counts = Counter(item["rarity"]["final_rarity"] for item in audited)
    fit_counts = {
        role: Counter(item["fit"][role] for item in audited) for role in FIT_ORDER
    }
    print(
        json.dumps(
            {
                "importable": len(audited),
                "held": len(held),
                "changes": len(change_log),
                "original_power": dict(sorted(original_power_counts.items())),
                "audited_power": dict(sorted(power_counts.items())),
                "rarity": dict(rarity_counts),
                "advisory_original_matches": advisory_matches_original,
                "advisory_audited_matches": advisory_matches_audited,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
