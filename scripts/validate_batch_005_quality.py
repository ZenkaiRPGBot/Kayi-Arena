"""Write the Batch 005 staged-completion report.

This does not validate JSON shape alone. It reports catalogue, artwork,
research, evaluation and publication readiness separately.
"""

from __future__ import annotations

import json
from pathlib import Path

from scripts.batch_005_quality import build_report, load_json

ROOT = Path("data")
REPORT = ROOT / "naruto_batch_005_completeness_report.json"


def main() -> None:
    catalogue = load_json(ROOT / "naruto_batch_005_catalogue.json") or {}
    manifest = load_json(ROOT / "naruto_batch_005_image_manifest.json") or {}
    research = load_json(ROOT / "naruto_batch_005_research.json") or {}
    evaluation = load_json(ROOT / "naruto_batch_005_original_claude_evaluation.json")
    report = build_report(catalogue, manifest, research, evaluation)
    REPORT.write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    stages = report["stages"]
    print(
        "catalogue={catalogue_complete} artwork={artwork_complete} "
        "research={research_complete} evaluation={evaluation_complete} "
        "publication={publication_ready}".format(
            catalogue_complete=stages["catalogue"]["complete"],
            artwork_complete=stages["artwork"]["complete"],
            research_complete=stages["research"]["complete"],
            evaluation_complete=stages["evaluation"]["complete"],
            publication_ready=stages["publication"]["ready"],
        )
    )
    print(f"wrote {REPORT}")


if __name__ == "__main__":
    main()
