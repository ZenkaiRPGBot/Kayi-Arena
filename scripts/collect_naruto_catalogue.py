"""Collect a Naruto/Shippuden candidate character catalogue."""

from __future__ import annotations

import argparse
from pathlib import Path

from app.content.catalogue import build_catalogue
from app.content.models import CandidateCatalogue
from app.content.providers.dattebayo import DattebayoProvider


def main() -> None:
    parser = argparse.ArgumentParser(description="Collect Naruto candidate characters from Dattebayo.")
    parser.add_argument("--output", default="data/naruto_candidates.json")
    parser.add_argument("--max-pages", type=int, default=None)
    args = parser.parse_args()

    provider = DattebayoProvider(max_pages=args.max_pages)
    candidates = provider.collect()
    catalogue = build_catalogue(
        universe="Naruto",
        provider_name=provider.name,
        source="dattebayo",
        candidates=candidates,
    )
    output = Path(args.output)
    catalogue.save(output)
    print(f"Wrote {len(catalogue.candidates)} candidates to {output}")
    print(catalogue.stats)


if __name__ == "__main__":
    main()
