"""Export the Naruto candidate catalogue to KA-IMPORT-1.0."""

from __future__ import annotations

import argparse
from pathlib import Path

from app.content.export import save_export
from app.content.models import CandidateCatalogue


def main() -> None:
    parser = argparse.ArgumentParser(description="Export Naruto candidates to KA-IMPORT-1.0.")
    parser.add_argument("--catalogue", default="data/naruto_candidates.json")
    parser.add_argument("--output", default="data/naruto_candidates_ka_import.json")
    parser.add_argument("--universe-id", default="naruto")
    args = parser.parse_args()

    catalogue = CandidateCatalogue.load(Path(args.catalogue))
    save_export(catalogue, Path(args.output), universe_id=args.universe_id)
    print(f"Wrote KA-IMPORT-1.0 export to {args.output}")


if __name__ == "__main__":
    main()
