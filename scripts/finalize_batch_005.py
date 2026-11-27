"""Finalise Stage 01 research and artwork records for Naruto Batch 005.

Reads the validated catalogue and the summary report produced by
``validate_naruto_images``, then writes a per-image manifest and refreshes
``image_status`` in the research package. No ratings are allocated.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

ROOT = Path("data")
CATALOGUE = ROOT / "naruto_batch_005_catalogue.json"
RESEARCH = ROOT / "naruto_batch_005_research.json"
SUMMARY_REPORT = ROOT / "naruto_batch_005_image_manifest.json"
IMAGE_DIR = ROOT / "naruto_images"

DIRECTLY_INSPECTED_PAGES = {
    "dattebayo:695": "source_page_inspected_2026-11-27",
    "dattebayo:901": "source_page_inspected_2026-11-27; corrected artwork URL",
}


def main() -> None:
    catalogue = json.loads(CATALOGUE.read_text(encoding="utf-8"))
    research = json.loads(RESEARCH.read_text(encoding="utf-8"))
    stats = json.loads(SUMMARY_REPORT.read_text(encoding="utf-8"))

    images = []
    candidates_without_valid_artwork = []
    research_by_id = {c["candidate_id"]: c for c in research["candidates"]}

    for candidate in catalogue["candidates"]:
        statuses = [img.get("status") for img in candidate.get("images", [])]
        if any(status == "valid" for status in statuses):
            image_status = "valid"
        elif any(status in {"pending", "duplicate"} for status in statuses):
            image_status = "partial"
        else:
            image_status = "missing"
            candidates_without_valid_artwork.append(
                {
                    "candidate_id": candidate["candidate_id"],
                    "name": candidate["name"],
                    "source_url": candidate.get("source_url", ""),
                    "attempted_urls": [img.get("url") for img in candidate.get("images", [])],
                }
            )

        record = research_by_id.get(candidate["candidate_id"])
        if record is not None:
            record["image_status"] = image_status

        identity_status = DIRECTLY_INSPECTED_PAGES.get(
            candidate["candidate_id"],
            "inspected_secondary; capability page reviewed in Stage 01B",
        )
        for index, img in enumerate(candidate.get("images", [])):
            status = img.get("status", "pending")
            safe_id = candidate["candidate_id"].replace(":", "_").replace("/", "_")
            local_path = None
            if status == "valid" and img.get("sha256") and img.get("format"):
                local_path = (
                    f"{IMAGE_DIR.as_posix()}/{safe_id}_{index}_{img['sha256'][:12]}.{img['format']}"
                )
            images.append(
                {
                    "candidate_id": candidate["candidate_id"],
                    "candidate_name": candidate["name"],
                    "candidate_source_url": candidate.get("source_url", ""),
                    "url": img.get("url"),
                    "source": img.get("source", candidate.get("source", "dattebayo")),
                    "status": status,
                    "source_accessible": status == "valid",
                    "format": img.get("format"),
                    "width": img.get("width"),
                    "height": img.get("height"),
                    "bytes": img.get("bytes"),
                    "sha256": img.get("sha256"),
                    "local_path": local_path,
                    "identity_review_status": identity_status,
                    "usage_permissions": img.get(
                        "rights", "source-dependent; review before publication"
                    ),
                    "error": img.get("error"),
                }
            )

    valid_candidates = sum(
        1
        for candidate in catalogue["candidates"]
        if any(img.get("status") == "valid" for img in candidate.get("images", []))
    )
    manifest = {
        "batch_id": "naruto-batch-005",
        "prepared_date": date.today().isoformat(),
        "stage": "01_research_and_catalogue_preparation",
        "source": "Dattebayo-derived image URLs on Fandom static hosting",
        "summary": {
            **stats,
            "candidates_total": len(catalogue["candidates"]),
            "candidates_with_valid_artwork": valid_candidates,
            "candidates_without_valid_artwork": len(candidates_without_valid_artwork),
        },
        "policies": {
            "identity_review": (
                "Exact catalogue-name matching was used for selection. Stage 01B reviewed each "
                "selected candidate's secondary character page for capability evidence. Artwork "
                "confirms the selected source record but is not feat evidence."
            ),
            "source_accessibility": (
                "true means the validated image was downloaded successfully by the existing image "
                "pipeline; no broader accessibility guarantee is implied."
            ),
            "usage_permissions": (
                "All images remain source-dependent. No publication permission was granted or claimed "
                "in Stage 01; usage must be reviewed before publication."
            ),
        },
        "candidates_without_valid_artwork": candidates_without_valid_artwork,
        "images": images,
    }

    SUMMARY_REPORT.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    RESEARCH.write_text(
        json.dumps(research, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(
        f"images={len(images)} valid_candidates={valid_candidates} "
        f"missing_candidates={len(candidates_without_valid_artwork)}"
    )
    print(f"wrote {SUMMARY_REPORT}")
    print(f"updated {RESEARCH}")


if __name__ == "__main__":
    main()
