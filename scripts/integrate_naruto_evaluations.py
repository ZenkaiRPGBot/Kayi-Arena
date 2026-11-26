"""Integrate Claude's 60 preliminary evaluations with the reconciled catalogue."""

from __future__ import annotations

import json
from pathlib import Path

from app.scoring.engine import score_record
from app.scoring.models import RatingInput
from app.scoring.rarity_v02 import classify_rarity_v02

ROLES = ["captain", "strategist", "attacker", "tank", "assassin", "support", "healer"]


def normalize(name: str) -> str:
    return " ".join(name.strip().lower().split())


def main() -> None:
    mapping = json.loads(Path("data/naruto_character_id_mapping.json").read_text(encoding="utf-8"))
    name_to_candidate = {normalize(m["target_name"]): m for m in mapping["mapping"]}

    catalogue = json.loads(Path("data/naruto_candidates.json").read_text(encoding="utf-8"))
    by_id = {c["candidate_id"]: c for c in catalogue["candidates"]}

    batches = [
        "data/naruto_evaluation_batch_001.json",
        "data/naruto_evaluation_batch_002_bulk.json",
    ]

    integrated = []
    issues = []
    rarity_counts = {}

    for batch_file in batches:
        batch = json.loads(Path(batch_file).read_text(encoding="utf-8"))
        for entry in batch["characters"]:
            name = entry["name"]
            m = name_to_candidate.get(normalize(name))
            if not m or m["status"] != "matched":
                issues.append({"name": name, "issue": "no catalogue match"})
                continue
            candidate_id = m["candidate_id"]
            candidate = by_id[candidate_id]

            power = int(entry["power"])
            fit = {r: int(entry["fit"][r]) for r in ROLES}

            # Calculate scores
            try:
                output = score_record(RatingInput(character_id=candidate_id, power=power, fit=fit))
                scores = dict(output.scores)
                scoring_version = output.scoring_version
            except Exception as exc:
                issues.append({"name": name, "issue": f"scoring failed: {exc}"})
                continue

            # Calculate rarity
            rarity_result = classify_rarity_v02(
                power=power,
                role_fits=fit,
                role_scores=scores,
                apply_naruto_healer_floor=True,
            )

            eval_status = entry.get("evaluation_status", "draft")
            held = eval_status == "held"

            record = {
                "character_id": candidate_id,
                "catalogue_name": candidate["name"],
                "claude_id": entry.get("id"),
                "name": name,
                "universe_id": "naruto",
                "aliases": entry.get("aliases", candidate.get("aliases", [])),
                "species": candidate.get("species"),
                "canonical_version": entry.get("canonical_version", candidate.get("debut", {})),
                "power": power,
                "fit": fit,
                "scores": scores,
                "scoring_version": scoring_version,
                "rarity": rarity_result.final_rarity,
                "rarity_detail": {
                    "version": rarity_result.version,
                    "rarity_points": rarity_result.rarity_points,
                    "base_rarity": rarity_result.base_rarity,
                    "final_rarity": rarity_result.final_rarity,
                    "highest_role_score": rarity_result.highest_role_score,
                    "combat_bonus": rarity_result.combat_bonus,
                    "specialist_bonus": rarity_result.specialist_bonus,
                    "versatility_bonus": rarity_result.versatility_bonus,
                    "floor_applied": rarity_result.floor_applied,
                },
                "confidence": entry.get("confidence"),
                "review_flags": entry.get("review_flags", []),
                "evaluation_status": eval_status,
                "held": held,
                "evidence": entry.get("evidence", []),
                "alternative_ratings": entry.get("alternative_ratings", []),
                "canonical_policy_version": entry.get("canonical_policy_version"),
                "rarity_rule_trace": entry.get("rarity_rule_trace"),
                "image_status": "pending",
                "image_verification": "unverified",
            }

            # Image verification issue check
            images = candidate.get("images", [])
            if not images:
                issues.append({"name": name, "issue": "no images in catalogue"})
            else:
                valid_images = [img for img in images if img.get("status") == "valid"]
                if not valid_images:
                    issues.append({"name": name, "issue": "no technically valid images"})

            integrated.append(record)
            rarity_counts[rarity_result.final_rarity] = rarity_counts.get(rarity_result.final_rarity, 0) + 1

    # Save integrated dataset (draft, unpublished)
    dataset = {
        "format_version": "KA-IMPORT-1.0",
        "batch_type": "evaluation_integrated",
        "universe_id": "naruto",
        "status": "draft",
        "record_count": len(integrated),
        "held_count": sum(1 for r in integrated if r["held"]),
        "characters": integrated,
        "issues": issues,
        "rarity_distribution": rarity_counts,
    }
    Path("data/naruto_evaluated_60_dataset.json").write_text(
        json.dumps(dataset, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    # Save report
    report = {
        "total_evaluated": len(integrated),
        "held": sum(1 for r in integrated if r["held"]),
        "draft": sum(1 for r in integrated if not r["held"]),
        "rarity_distribution": rarity_counts,
        "issues": issues,
        "missing_ratings": [i for i in issues if "scoring failed" in i["issue"]],
    }
    Path("data/naruto_evaluation_integration_report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    print(f"Integrated {len(integrated)} records, {report['held']} held, {len(issues)} issues")
    print("Rarity:", rarity_counts)


if __name__ == "__main__":
    main()
