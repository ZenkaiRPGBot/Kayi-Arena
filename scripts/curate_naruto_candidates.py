"""Prepare a larger curated Naruto/Shippuden candidate roster."""

from __future__ import annotations

import json
import re
from pathlib import Path

GROUPS = [
    "ready_for_evaluation",
    "insufficient_canonical_evidence",
    "canon_or_eligibility_disputed",
    "duplicate_or_alternate_version",
    "filler_exclusive",
    "image_requires_review",
    "excluded_with_reason",
]


def classify(candidate: dict) -> str:
    name = candidate.get("name", "")
    notes = " ".join(candidate.get("notes", []))
    eligibility = candidate.get("canonical_eligibility", "uncertain")
    images = candidate.get("image_urls", [])
    universe = candidate.get("universe", "")

    if universe == "Boruto":
        return "excluded_with_reason"  # separated for review, not Naruto/Shippuden core

    if "filler" in notes.lower() or "anime-only" in notes.lower() or "anime only" in notes.lower():
        return "filler_exclusive"

    if re.search(r"\b(II|III|IV|V)\b", name) or "Manda II" in name:
        return "duplicate_or_alternate_version"

    if eligibility != "eligible":
        return "canon_or_eligibility_disputed"

    if not images:
        return "insufficient_canonical_evidence"

    # Non-human species or special notes -> image review
    species = (candidate.get("species") or "").lower()
    if species not in {"human", "none", ""}:
        return "image_requires_review"

    # Candidates with only one image or unknown dimensions -> review
    if len(images) == 1:
        return "image_requires_review"

    return "ready_for_evaluation"


def main() -> None:
    catalogue = json.loads(Path("data/naruto_candidates.json").read_text(encoding="utf-8"))
    naruto_candidates = [c for c in catalogue["candidates"] if c.get("universe") == "Naruto"]

    groups = {g: [] for g in GROUPS}
    for candidate in naruto_candidates:
        group = classify(candidate)
        entry = {
            "candidate_id": candidate["candidate_id"],
            "name": candidate["name"],
            "group": group,
            "canonical_eligibility": candidate.get("canonical_eligibility"),
            "image_count": len(candidate.get("image_urls", [])),
            "species": candidate.get("species"),
            "notes": candidate.get("notes", []),
        }
        groups[group].append(entry)

    payload = {
        "source": "naruto_candidates.json",
        "total_naruto_candidates": len(naruto_candidates),
        "groups": {g: groups[g] for g in GROUPS},
        "stats": {g: len(groups[g]) for g in GROUPS},
    }
    Path("data/naruto_curated_candidates.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(payload["stats"])


if __name__ == "__main__":
    main()
