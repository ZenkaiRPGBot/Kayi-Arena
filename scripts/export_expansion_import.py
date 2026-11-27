"""Export the evaluated expansion batch to KA-IMPORT-1.0.

Draft records are importable with computed rarity/power/fit.  Held records are
kept in a separate, explicitly non-importable list so unknown ratings are never
coerced into zero or a placeholder rarity.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path("data")
DATASET = ROOT / "naruto_expansion_003_004_evaluated_dataset.json"
CATALOGUE = ROOT / "naruto_expansion_003_004_catalogue.json"
OUT = ROOT / "naruto_expansion_003_004_ka_import.json"

GRADE = {
    "catalogue_metadata": "A",
    "secondary_source": "B",
    "search_result_summary": "B",
    "recollection_only": "C",
}


def evidence_payload(record: dict) -> list[dict]:
    payload = []
    for item in record.get("evidence") or []:
        level = str(item.get("verification_level", "unverified"))
        payload.append(
            {
                "target": "overall",
                "grade": GRADE.get(level, "C"),
                "source_ref": item.get("url") or item.get("source_note") or "",
                "summary": item.get("lead") or "",
                "verification_level": level,
            }
        )
    return payload


def image_payload(record: dict) -> dict | None:
    image = record.get("image")
    if not image:
        return None
    mime = f"image/{image['format']}" if image.get("format") else ""
    return {
        "url_or_ref": image.get("url"),
        "source_ref": image.get("source", "dattebayo"),
        "mime_type": mime,
        "width": image.get("width"),
        "height": image.get("height"),
        "checksum": f"sha256-{image['sha256']}" if image.get("sha256") else "",
        "status": "pending",
        "validation_status": image.get("status"),
        "rights": image.get("rights", "source-dependent; review before publication"),
    }


def main() -> None:
    dataset = json.loads(DATASET.read_text(encoding="utf-8"))
    catalogue = json.loads(CATALOGUE.read_text(encoding="utf-8"))
    by_id = {c["candidate_id"]: c for c in catalogue["candidates"]}

    importable = []
    held = []
    for record in dataset["characters"]:
        candidate = by_id.get(record["character_id"], {})
        common = {
            "character_id": record["character_id"].replace(":", "_"),
            "name": record["name"],
            "aliases": record.get("aliases") or [],
            "species": "non_human" if candidate.get("species") else "human",
            "canonical_version": record.get("canonical_version") or "unresolved",
            "batch": record["batch"],
            "source_references": [
                f"source:{candidate.get('source', 'dattebayo')}",
                f"profile:{candidate.get('source_url', '')}",
            ],
            "evidence": evidence_payload(record),
            "revision_ref": "expansion-003-004",
            "review_status": "pending",
            "review_flags": record.get("review_flags") or [],
        }
        image = image_payload(record)
        if image:
            common["image"] = image

        if record.get("held"):
            held.append(
                {
                    **common,
                    "importable": False,
                    "evaluation_status": "held",
                    "rarity": None,
                    "power": None,
                    "fit": None,
                    "scores": None,
                    "power_reference": record.get("power"),
                    "fit_reference": record.get("fit"),
                    "scores_reference": record.get("scores"),
                    "rarity_reference": record.get("rarity"),
                    "held_reason": (
                        "Ratings incomplete or identity/eligibility unresolved; "
                        "must not be imported as a playable record. Reference values, "
                        "where present, are not importable ratings."
                    ),
                }
            )
            continue

        importable.append(
            {
                **common,
                "importable": True,
                "evaluation_status": "draft",
                "rarity": record["rarity"],
                "power": record["power"],
                "fit": record["fit"],
                "scores": record.get("scores"),
                "rarity_detail": record.get("rarity_detail"),
            }
        )

    payload = {
        "format_version": "KA-IMPORT-1.0",
        "batch_type": "catalogue",
        "universe_id": "naruto",
        "batch_id": "naruto-expansion-003-004",
        "status": "draft",
        "scoring_version": "SCORE-1.0",
        "rarity_version": "RARITY-0.2",
        "notes": [
            "Draft records are evaluated and import-ready but remain pending human review.",
            "Held records are listed separately with importable=false and null ratings.",
            "No record is approved or published by this batch.",
        ],
        "character_count": len(importable),
        "held_count": len(held),
        "characters": importable,
        "held_records": held,
    }
    OUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {OUT}: {len(importable)} importable, {len(held)} held")


if __name__ == "__main__":
    main()
