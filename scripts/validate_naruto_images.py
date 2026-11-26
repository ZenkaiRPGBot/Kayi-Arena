"""Validate and download images for a candidate catalogue."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.content.images import process_catalogue_images
from app.content.models import CandidateCatalogue


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate Naruto candidate images.")
    parser.add_argument("--catalogue", default="data/naruto_candidates.json")
    parser.add_argument("--output-dir", default="data/naruto_images")
    parser.add_argument("--report", default="data/naruto_image_report.json")
    parser.add_argument("--no-download", action="store_true")
    parser.add_argument("--concurrency", type=int, default=8)
    parser.add_argument("--timeout", type=float, default=15.0)
    args = parser.parse_args()

    catalogue = CandidateCatalogue.load(Path(args.catalogue))
    stats = process_catalogue_images(
        catalogue,
        output_dir=Path(args.output_dir),
        download=not args.no_download,
        timeout=args.timeout,
        concurrency=args.concurrency,
    )
    catalogue.save(Path(args.catalogue))
    Path(args.report).parent.mkdir(parents=True, exist_ok=True)
    Path(args.report).write_text(json.dumps(stats, indent=2), encoding="utf-8")
    print(stats)


if __name__ == "__main__":
    main()
