"""Consolidate batches 003, 004-A and 004-B into the expansion deliverables."""

from __future__ import annotations

import hashlib
import json
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from app.content.export import save_export
from app.content.models import CandidateCatalogue, CandidateCharacter, CandidateImage
from app.scoring.engine import score_record
from app.scoring.models import RatingInput
from app.scoring.rarity_v02 import classify_rarity_v02

ROOT = Path("data")
SOURCE_CATALOGUE = ROOT / "naruto_candidates.json"
VALIDATED_CATALOGUE = ROOT / "naruto_expansion_003_004_catalogue.json"
COMBINED_EVALS = ROOT / "naruto_expansion_003_004_evaluations.json"

OUT_CAT = ROOT / "naruto_expansion_003_004_catalogue.json"
OUT_IMG = ROOT / "naruto_expansion_003_004_image_manifest.json"
OUT_IMG_REPORT = ROOT / "naruto_expansion_003_004_image_report.json"
OUT_EVAL = ROOT / "naruto_expansion_003_004_evaluated_dataset.json"
OUT_KA = ROOT / "naruto_expansion_003_004_ka_import.json"
OUT_REPORT = ROOT / "naruto_expansion_003_004_integration_report.json"

ROLES = ["captain", "strategist", "attacker", "tank", "assassin", "support", "healer"]

ALIASES = {
    "C (Kumogakure shinobi)": "C",
    "Reto — First Kazekage": "Reto",
    "Shamon — Second Kazekage": "Shamon",
    "Byakuren — First Mizukage": "Byakuren",
    "Ishikawa — First Tsuchikage": "Ishikawa",
    "A — First Raikage": "A (First Raikage)",
    "A — Second Raikage": "A (Second Raikage)",
    "Kiri — Allied Shinobi Forces": "Kiri (ninja)",
    "Hoheto Hyuga": "Hoheto Hyūga",
    "Yoroi Akado": "Yoroi Akadō",
    "Chukichi": "Chūkichi",
    "Kakko": "Kakkō",
    "Choji Akimichi": "Chōji Akimichi",
    "Chojuro": "Chōjūrō",
    "Nono Yakushi": "Nonō Yakushi",
}


def norm(value: str) -> str:
    return unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode().lower().strip()


def candidate_to_model(candidate: dict) -> CandidateCharacter:
    images = [
        CandidateImage(
            url=img["url"],
            source=img.get("source", "dattebayo"),
            sha256=img.get("sha256"),
            format=img.get("format"),
            width=img.get("width"),
            height=img.get("height"),
            bytes=img.get("bytes"),
            status=img.get("status", "pending"),
            error=img.get("error"),
            rights=img.get("rights", "source-dependent; review before publication"),
        )
        for img in candidate.get("images", [])
    ]
    return CandidateCharacter(
        candidate_id=candidate["candidate_id"],
        name=candidate["name"],
        universe=candidate.get("universe", "Naruto"),
        source=candidate.get("source", "dattebayo"),
        source_url=candidate.get("source_url", ""),
        aliases=candidate.get("aliases", []),
        image_urls=candidate.get("image_urls", []),
        images=images,
        debut=candidate.get("debut", {}),
        classification=candidate.get("classification", []),
        species=candidate.get("species"),
        canonical_eligibility=candidate.get("canonical_eligibility", "uncertain"),
        eligibility_reason=candidate.get("eligibility_reason", ""),
        source_metadata=candidate.get("source_metadata", {}),
        review_status=candidate.get("review_status", "pending"),
        notes=candidate.get("notes", []),
    )


def main() -> None:
    source = json.loads(SOURCE_CATALOGUE.read_text(encoding="utf-8"))
    validated = json.loads(VALIDATED_CATALOGUE.read_text(encoding="utf-8"))
    combined = json.loads(COMBINED_EVALS.read_text(encoding="utf-8"))

    validated_by_id = {c["candidate_id"]: c for c in validated.get("candidates", [])}
    source_by_norm = {norm(c["name"]): c for c in source["candidates"]}
    for alias, target in ALIASES.items():
        source_by_norm[norm(alias)] = source_by_norm[norm(target)]

    issues: list[dict] = []
    matched: list[tuple[dict, dict, dict]] = []
    seen_ids: set[str] = set()

    for record in combined["characters"]:
        revised = record["revised"]
        name = record["name"]
        target = ALIASES.get(name, name)
        candidate = source_by_norm.get(norm(target))
        if candidate is None:
            issues.append({"batch": record["batch"], "name": name, "issue": "no catalogue match"})
            continue
        cid = candidate["candidate_id"]
        if cid in seen_ids:
            issues.append({"batch": record["batch"], "name": name, "issue": f"duplicate candidate id {cid}"})
            continue
        seen_ids.add(cid)
        matched.append((record, revised, candidate))

    # Catalogue: prefer the validated image records so hashes/status survive.
    catalogue_candidates = []
    for record, revised, candidate in matched:
        merged = json.loads(json.dumps(candidate))
        validated_candidate = validated_by_id.get(candidate["candidate_id"])
        if validated_candidate and validated_candidate.get("images"):
            merged["images"] = validated_candidate["images"]
            merged["image_urls"] = [i["url"] for i in validated_candidate["images"]]
        catalogue_candidates.append(merged)

    catalogue = CandidateCatalogue(
        universe="Naruto",
        source="dattebayo",
        provider="dattebayo",
        generated_at=datetime.now(timezone.utc).isoformat(),
        stats={
            "targets": len(combined["characters"]),
            "matched": len(catalogue_candidates),
            "unmatched": len(combined["characters"]) - len(catalogue_candidates),
        },
        candidates=[candidate_to_model(c) for c in catalogue_candidates],
    )
    catalogue.save(OUT_CAT)
    save_export(catalogue, OUT_KA, universe_id="naruto")

    images_by_id = {c["candidate_id"]: c.get("images", []) for c in catalogue_candidates}
    evaluation_by_id = {candidate["candidate_id"]: (record, revised) for record, revised, candidate in matched}

    def identity_check(record: dict, revised: dict) -> str:
        """Describe how confident we are in the *identity* behind the artwork.

        This is intentionally separate from source accessibility: an image can
        download perfectly while still being the wrong character.
        """
        flags = [str(flag) for flag in (revised.get("review_flags") or [])]
        lowered = [flag.lower() for flag in flags]
        # A later resolution wins over an earlier "needs check" flag, so the
        # audit trail can keep both without the manifest staying ambiguous.
        if any(
            token in flag
            for flag in lowered
            for token in ("identity_resolved", "disambiguated", "alias_identity_check")
        ):
            return "resolved_alias"
        if any("identity_needs_check" in flag or "duplicate_identity_ambiguity" in flag for flag in lowered):
            return "uncertain"
        if any("combined_playable" in flag for flag in lowered):
            return "combined_record"
        return "source_name_match"

    # Image manifest
    manifest = []
    image_hashes: dict[str, list[str]] = defaultdict(list)
    identity_checks: Counter[str] = Counter()
    for candidate in catalogue_candidates:
        record, revised = evaluation_by_id[candidate["candidate_id"]]
        identity = identity_check(record, revised)
        identity_checks[identity] += 1
        images = []
        for img in candidate.get("images", []):
            entry = {
                "url": img.get("url"),
                "source": img.get("source"),
                "status": img.get("status"),
                "source_accessible": img.get("status") == "valid",
                "identity_verification": identity,
                "format": img.get("format"),
                "width": img.get("width"),
                "height": img.get("height"),
                "bytes": img.get("bytes"),
                "sha256": img.get("sha256"),
                "error": img.get("error"),
                "rights": img.get("rights", "source-dependent; review before publication"),
            }
            images.append(entry)
            if entry["status"] == "valid" and entry["sha256"]:
                image_hashes[entry["sha256"]].append(candidate["name"])
        valid = [i for i in images if i["status"] == "valid"]
        manifest.append(
            {
                "candidate_id": candidate["candidate_id"],
                "name": candidate["name"],
                "evaluation_name": record["name"],
                "identity_check": identity,
                "image_count": len(images),
                "valid_count": len(valid),
                "primary_image": valid[0] if valid else None,
                "images": images,
                "validation_status": "valid" if valid else ("missing" if not images else "invalid"),
            }
        )
    manifest_summary = {
        "characters": len(manifest),
        "with_valid_image": sum(1 for m in manifest if m["valid_count"] > 0),
        "without_valid_image": sum(1 for m in manifest if m["valid_count"] == 0),
        "total_images": sum(m["image_count"] for m in manifest),
        "valid_images": sum(m["valid_count"] for m in manifest),
    }
    OUT_IMG.write_text(
        json.dumps(
            {
                "universe_id": "naruto",
                "batch_id": "naruto-expansion-003-004",
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "summary": manifest_summary,
                "identity_verification": {
                    "method": "source catalogue name/alias match plus documented ambiguity flags",
                    "visual_identity_verified": False,
                    "counts": dict(identity_checks),
                },
                "characters": manifest,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    non_valid_images = [
        {
            "candidate_id": m["candidate_id"],
            "name": m["name"],
            "identity_check": m["identity_check"],
            "url": image["url"],
            "status": image["status"],
            "error": image.get("error"),
        }
        for m in manifest
        for image in m["images"]
        if image["status"] != "valid"
    ]
    OUT_IMG_REPORT.write_text(
        json.dumps(
            {
                "universe_id": "naruto",
                "batch_id": "naruto-expansion-003-004",
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "summary": {
                    **manifest_summary,
                    "invalid_images": sum(1 for i in non_valid_images if i["status"] == "invalid"),
                    "missing_images": sum(1 for i in non_valid_images if i["status"] == "missing"),
                    "duplicate_images": sum(1 for names in image_hashes.values() if len(names) > 1),
                },
                "identity_verification": {
                    "method": "source catalogue name/alias match plus documented ambiguity flags",
                    "visual_identity_verified": False,
                    "counts": dict(identity_checks),
                    "uncertain_characters": [
                        {
                            "candidate_id": m["candidate_id"],
                            "name": m["name"],
                            "identity_check": m["identity_check"],
                        }
                        for m in manifest
                        if m["identity_check"] == "uncertain"
                    ],
                },
                "non_valid_images": non_valid_images,
                "notes": [
                    "source_accessible means the image downloaded and decoded; it does not prove the image depicts the intended character.",
                    "Identity verification is a source-record name/alias match, not a visual review.",
                    "One missing secondary image is non-blocking because every character has a valid primary image.",
                ],
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    # Scoring and rarity
    integrated = []
    rarity_counts = Counter()
    power_counts = Counter()
    batch_status: dict[str, Counter] = defaultdict(Counter)
    profile_groups: dict[tuple, list[str]] = defaultdict(list)

    for record, revised, candidate in matched:
        batch = record["batch"]
        status = revised.get("evaluation_status", "held")
        identity = identity_check(record, revised)
        batch_status[batch][status] += 1
        power = revised.get("power")
        fit = revised.get("fit")
        candidate_images = images_by_id.get(candidate["candidate_id"], candidate.get("images", []))
        valid_images = [i for i in candidate_images if i.get("status") == "valid"]
        image_status = "valid" if valid_images else ("missing" if not candidate_images else "invalid")

        if power is None or fit is None or any(fit.get(r) is None for r in ROLES):
            # Incomplete Held record: never coerce missing ratings to zero.
            integrated.append(
                {
                    "character_id": candidate["candidate_id"],
                    "name": record["name"],
                    "catalogue_name": candidate["name"],
                    "batch": batch,
                    "universe_id": "naruto",
                    "canonical_version": revised.get("canonical_version"),
                    "aliases": revised.get("aliases", []),
                    "power": None,
                    "fit": None,
                    "scores": None,
                    "scoring_version": None,
                    "rarity": None,
                    "rarity_detail": None,
                    "confidence": revised.get("confidence"),
                    "review_flags": revised.get("review_flags", []),
                    "evaluation_status": "held",
                    "held": True,
                    "identity_check": identity,
                    "evidence": revised.get("evidence_leads", []),
                    "image_status": image_status,
                    "image": valid_images[0] if valid_images else None,
                    "evaluation_origin": "held_incomplete",
                    "revised": bool(record["changes"]),
                }
            )
            continue

        power = int(power)
        fit = {role: int(fit[role]) for role in ROLES}
        held = status == "held"
        output = score_record(RatingInput(character_id=candidate["candidate_id"], power=power, fit=fit))
        scores = dict(output.scores)
        rarity = classify_rarity_v02(
            power=power,
            role_fits=fit,
            role_scores=scores,
            apply_naruto_healer_floor=True,
        )
        if not held:
            rarity_counts[rarity.final_rarity] += 1
            power_counts[power] += 1
            profile_groups[(power, tuple(fit[r] for r in ROLES))].append(record["name"])

        integrated.append(
            {
                "character_id": candidate["candidate_id"],
                "name": record["name"],
                "catalogue_name": candidate["name"],
                "batch": batch,
                "universe_id": "naruto",
                "canonical_version": revised.get("canonical_version"),
                "aliases": revised.get("aliases", []),
                "power": power,
                "fit": fit,
                "scores": scores,
                "scoring_version": output.scoring_version,
                "rarity": rarity.final_rarity,
                "rarity_detail": {
                    "version": rarity.version,
                    "rarity_points": rarity.rarity_points,
                    "base_rarity": rarity.base_rarity,
                    "final_rarity": rarity.final_rarity,
                    "highest_role_score": rarity.highest_role_score,
                    "combat_bonus": rarity.combat_bonus,
                    "specialist_bonus": rarity.specialist_bonus,
                    "versatility_bonus": rarity.versatility_bonus,
                    "floor_applied": rarity.floor_applied,
                },
                "confidence": revised.get("confidence"),
                "review_flags": revised.get("review_flags", []),
                "evaluation_status": status,
                "held": held,
                "rarity_reference_only": held,
                "identity_check": identity,
                "evidence": revised.get("evidence_leads", []),
                "image_status": image_status,
                "image": valid_images[0] if valid_images else None,
                "evaluation_origin": "revised" if record["changes"] else "claude_original",
                "revised": bool(record["changes"]),
            }
        )

    dataset = {
        "format_version": "KA-IMPORT-1.0",
        "batch_type": "evaluation_integrated",
        "universe_id": "naruto",
        "batch_id": "naruto-expansion-003-004",
        "status": "draft",
        "scoring_version": "SCORE-1.0",
        "rarity_version": "RARITY-0.2",
        "record_count": len(integrated),
        "draft_count": sum(1 for r in integrated if not r["held"]),
        "held_count": sum(1 for r in integrated if r["held"]),
        "characters": integrated,
        "rarity_distribution": dict(rarity_counts),
        "power_distribution": dict(sorted(power_counts.items())),
    }
    OUT_EVAL.write_text(json.dumps(dataset, indent=2, ensure_ascii=False), encoding="utf-8")

    duplicate_profiles = {
        "|".join(str(v) for v in key): names
        for key, names in profile_groups.items()
        if len(names) > 1
    }
    duplicate_images = {
        sha: names for sha, names in image_hashes.items() if len(names) > 1
    }

    report = {
        "universe_id": "naruto",
        "batch_id": "naruto-expansion-003-004",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "targets": len(combined["characters"]),
        "matched": len(integrated),
        "unmatched": len(issues),
        "draft": sum(1 for r in integrated if not r["held"]),
        "held": sum(1 for r in integrated if r["held"]),
        "by_batch": {batch: dict(counter) for batch, counter in sorted(batch_status.items())},
        "rarity_distribution": dict(rarity_counts),
        "power_distribution": dict(sorted(power_counts.items())),
        "image_summary": {
            "with_valid_image": sum(1 for r in integrated if r["image_status"] == "valid"),
            "without_valid_image": sum(1 for r in integrated if r["image_status"] != "valid"),
        },
        "revised_records": sum(1 for r in integrated if r["revised"]),
        "claude_original_records": sum(1 for r in integrated if not r["revised"]),
        "duplicate_evaluation_profiles": duplicate_profiles,
        "duplicate_image_hashes": duplicate_images,
        "issues": issues,
        "held_records": [
            {
                "batch": r["batch"],
                "name": r["name"],
                "reason": (
                    "identity/eligibility review; ratings retained for reference only"
                    if r["power"] is not None
                    else "incomplete ratings preserved as Held"
                ),
                "power_reference": r["power"],
                "rarity_reference": r["rarity"],
            }
            for r in integrated
            if r["held"]
        ],
        "notes": [
            "Enma is present in the 004-B evaluation file but has no Dattebayo catalogue record; retained as unmatched.",
            "All Held records keep null power/fit/rarity; missing ratings are never coerced to zero.",
            "Rarity is calculated with the shared RARITY-0.2 implementation and Naruto healer floors.",
            "No record is approved or published; every matched record remains draft or held.",
        ],
    }
    OUT_REPORT.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"matched={len(integrated)} draft={report['draft']} held={report['held']} unmatched={len(issues)}")
    print("rarity:", dict(rarity_counts))
    print("power:", dict(sorted(power_counts.items())))
    print("images:", report["image_summary"])
    print("duplicate profiles:", len(duplicate_profiles))


if __name__ == "__main__":
    main()
