"""Prepare evaluation-ready candidate batches beyond the initial 60."""

from __future__ import annotations

import json
from pathlib import Path

BATCH_SIZE = 50


def main() -> None:
    curated = json.loads(Path("data/naruto_curated_candidates.json").read_text(encoding="utf-8"))
    catalogue = json.loads(Path("data/naruto_candidates.json").read_text(encoding="utf-8"))
    by_id = {c["candidate_id"]: c for c in catalogue["candidates"]}

    # Select candidates: ready first, then image_requires_review, then others with images
    priority_order = ["ready_for_evaluation", "image_requires_review", "insufficient_canonical_evidence", "canon_or_eligibility_disputed"]
    selected = []
    for group in priority_order:
        for entry in curated["groups"].get(group, []):
            if len(selected) >= 130:
                break
            selected.append(entry)
        if len(selected) >= 130:
            break

    # Build batches
    batches = [selected[i:i+BATCH_SIZE] for i in range(0, len(selected), BATCH_SIZE)]
    for idx, batch in enumerate(batches, start=3):
        chars = []
        for entry in batch:
            c = by_id[entry["candidate_id"]]
            chars.append({
                "id": c["candidate_id"].replace(":", "_"),
                "name": c["name"],
                "aliases": c.get("aliases", []),
                "canonical_version": c.get("debut", {}).get("manga") or c.get("debut", {}).get("anime") or "unknown",
                "power": None,
                "fit": None,
                "rarity": None,
                "review_flags": c.get("notes", []),
                "evaluation_status": "draft",
                "image_available": bool(c.get("image_urls")),
                "source_references": [f"profile:{c['source_url']}"],
            })
        payload = {
            "format_version": "KA-IMPORT-1.0",
            "batch_type": "catalogue",
            "universe_id": "naruto",
            "batch_id": f"naruto_candidate_batch_{idx:03d}",
            "batch_status": "draft",
            "characters": chars,
        }
        out = Path(f"data/naruto_candidate_batch_{idx:03d}.json")
        out.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"Wrote {out} with {len(chars)} candidates")


if __name__ == "__main__":
    main()
