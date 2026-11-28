"""Record artwork failures so the corrected build can omit those candidates.

The script combines failures detected in the Stage 01 manifest with manual
review decisions that cannot be inferred from the final manifest.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path("data")
MANIFEST = ROOT / "naruto_batch_005_image_manifest.json"
OUT = ROOT / "naruto_batch_005_artwork_exclusions.json"

MANUAL_EXCLUSIONS = {
    "dattebayo:855": (
        "Source image URL returns HTTP 404 and the inspected page has no single-character "
        "infobox image; preserved as unresolved rather than substituted with a group image."
    )
}


def main() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    images = manifest.get("images") or []
    by_candidate: dict[str, list[dict]] = {}
    for image in images:
        by_candidate.setdefault(str(image.get("candidate_id") or ""), []).append(image)

    exclusions: dict[str, str] = dict(MANUAL_EXCLUSIONS)
    for candidate_id, records in by_candidate.items():
        statuses = [str(item.get("status") or "") for item in records]
        if any(status == "valid" for status in statuses):
            continue
        errors = sorted({str(item.get("error") or status) for item, status in zip(records, statuses)})
        exclusions[candidate_id] = "No validated artwork: " + "; ".join(errors or statuses)

    OUT.write_text(json.dumps(exclusions, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"excluded={len(exclusions)} wrote={OUT}")


if __name__ == "__main__":
    main()
