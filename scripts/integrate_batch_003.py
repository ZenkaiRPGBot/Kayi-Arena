"""Integrate batch 003 evaluations with scoring and rarity."""

from __future__ import annotations

import json
from pathlib import Path

from app.scoring.engine import score_record
from app.scoring.models import RatingInput
from app.scoring.rarity_v02 import classify_rarity_v02

ROLES = ["captain", "strategist", "attacker", "tank", "assassin", "support", "healer"]


def normalize(name: str) -> str:
    import unicodedata
    return unicodedata.normalize('NFKD', name).encode('ascii', 'ignore').decode().lower().strip()


def main() -> None:
    eval_file = Path("data/naruto_batch_003_evaluations_revised.json")
    if not eval_file.exists():
        eval_file = Path("data/naruto_batch_003_evaluations.json")

    batch = json.loads(eval_file.read_text(encoding="utf-8"))
    catalogue = json.loads(Path("data/naruto_batch_003_catalogue.json").read_text(encoding="utf-8"))
    by_name = {normalize(c["name"]): c for c in catalogue["candidates"]}

    integrated = []
    issues = []
    rarity_counts = {}

    for entry in batch["characters"]:
        name = entry["name"]
        c = by_name.get(normalize(name))
        if not c:
            issues.append({"name": name, "issue": "no catalogue match"})
            continue
        candidate_id = c["candidate_id"]
        power = int(entry["power"])
        fit = {r: int(entry["fit"][r]) for r in ROLES}

        try:
            output = score_record(RatingInput(character_id=candidate_id, power=power, fit=fit))
            scores = dict(output.scores)
            scoring_version = output.scoring_version
        except Exception as exc:
            issues.append({"name": name, "issue": f"scoring failed: {exc}"})
            continue

        rarity_result = classify_rarity_v02(
            power=power,
            role_fits=fit,
            role_scores=scores,
            apply_naruto_healer_floor=True,
        )

        eval_status = entry.get("evaluation_status", "draft")
        held = eval_status == "held"

        # Image status
        images = c.get("images", [])
        valid_images = [img for img in images if img.get("status") == "valid"]
        if not images:
            issues.append({"name": name, "issue": "no images in catalogue"})
        elif not valid_images:
            issues.append({"name": name, "issue": "no technically valid images"})

        record = {
            "character_id": candidate_id,
            "name": name,
            "universe_id": "naruto",
            "canonical_version": entry.get("canonical_version"),
            "aliases": entry.get("aliases", []),
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
            "evidence": entry.get("evidence_leads", []),
            "image_status": "valid" if valid_images else ("missing" if not images else "invalid"),
            "source_url": c.get("source_url"),
        }
        integrated.append(record)
        rarity_counts[rarity_result.final_rarity] = rarity_counts.get(rarity_result.final_rarity, 0) + 1

    dataset = {
        "format_version": "KA-IMPORT-1.0",
        "batch_type": "evaluation_integrated",
        "universe_id": "naruto",
        "batch_id": "naruto_batch_003",
        "status": "draft",
        "record_count": len(integrated),
        "held_count": sum(1 for r in integrated if r["held"]),
        "characters": integrated,
        "issues": issues,
        "rarity_distribution": rarity_counts,
    }
    Path("data/naruto_batch_003_evaluated_dataset.json").write_text(
        json.dumps(dataset, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    report = {
        "total_evaluated": len(integrated),
        "held": sum(1 for r in integrated if r["held"]),
        "draft": sum(1 for r in integrated if not r["held"]),
        "rarity_distribution": rarity_counts,
        "issues": issues,
    }
    Path("data/naruto_batch_003_integration_report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    print(f"Integrated {len(integrated)} records, {report['held']} held, {len(issues)} issues")
    print("Rarity:", rarity_counts)


if __name__ == "__main__":
    main()
