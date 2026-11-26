"""Reconcile the 60 priority Naruto characters against the collected catalogue."""

from __future__ import annotations

import json
from pathlib import Path

TARGETS = [
    "Naruto Uzumaki", "Sasuke Uchiha", "Madara Uchiha", "Shikamaru Nara", "Tsunade",
    "Sakura Haruno", "Kakashi Hatake", "Rock Lee", "Kurama", "Katsuyu",
    "Hashirama Senju", "Kaguya Otsutsuki", "Hagoromo Otsutsuki", "Obito Uchiha", "Nagato",
    "Minato Namikaze", "Tobirama Senju", "Itachi Uchiha", "Hamura Otsutsuki", "Indra Otsutsuki",
    "Ashura Otsutsuki", "Gyuki", "Hiruzen Sarutobi", "Jiraiya", "Orochimaru", "Might Guy",
    "Kabuto Yakushi", "Gaara", "Killer B", "Onoki", "Mu", "Gengetsu Hozuki", "Third Raikage",
    "Fourth Raikage", "Kisame Hoshigaki", "Sasori", "Deidara", "Kakuzu", "Konan", "Danzo Shimura",
    "Chiyo", "Hanzo", "Mei Terumi", "Third Kazekage", "Kushina Uzumaki", "Shisui Uchiha",
    "Black Zetsu", "Sakumo Hatake", "Izuna Uchiha", "Shukaku", "Matatabi", "Isobu", "Son Goku",
    "Kokuo", "Saiken", "Chomei", "Gamabunta", "Manda", "Fukasaku", "Shima",
]

# Manual alias map from target name to exact catalogue name.
ALIASES = {
    "Kaguya Otsutsuki": "Kaguya Ōtsutsuki",
    "Hagoromo Otsutsuki": "Hagoromo Ōtsutsuki",
    "Hamura Otsutsuki": "Hamura Ōtsutsuki",
    "Indra Otsutsuki": "Indra Ōtsutsuki",
    "Ashura Otsutsuki": "Asura Ōtsutsuki",
    "Gyuki": "Gyūki",
    "Onoki": "Ōnoki",
    "Mu": "Mū",
    "Gengetsu Hozuki": "Gengetsu Hōzuki",
    "Mei Terumi": "Mei Terumī",
    "Son Goku": "Son Gokū",
    "Kokuo": "Kokuō",
    "Saiken": "Saiken",
    "Chomei": "Chōmei",
    "Kurama": "Kurama",
    "Hanzo": "Hanzō",
    "Danzo Shimura": "Danzō Shimura",
    "Killer B": "Killer B",
    "Third Raikage": "A (Third Raikage)",
    "Fourth Raikage": "A (Fourth Raikage)",
    "Black Zetsu": "Black Zetsu",
}


def normalize(name: str) -> str:
    return " ".join(name.strip().lower().split())


def main() -> None:
    catalogue = json.loads(Path("data/naruto_candidates.json").read_text(encoding="utf-8"))
    by_name = {normalize(c["name"]): c for c in catalogue["candidates"]}

    mapping = []
    matched_candidates = []
    unmatched = []

    for target in TARGETS:
        resolved_name = ALIASES.get(target, target)
        candidate = by_name.get(normalize(resolved_name))
        if candidate is not None:
            mapping.append({
                "target_name": target,
                "catalogue_name": candidate["name"],
                "candidate_id": candidate["candidate_id"],
                "provider": candidate["source"],
                "provider_id": candidate["source_metadata"].get("dattebayo_id"),
                "universe": candidate["universe"],
                "status": "matched",
                "aliases": candidate.get("aliases", []),
                "source_url": candidate["source_url"],
                "image_count": len(candidate.get("image_urls", [])),
                "canonical_eligibility": candidate["canonical_eligibility"],
                "review_status": candidate["review_status"],
            })
            matched_candidates.append(candidate)
        else:
            mapping.append({
                "target_name": target,
                "catalogue_name": None,
                "candidate_id": None,
                "status": "unmatched",
                "notes": "No exact catalogue match; manual resolution required.",
            })
            unmatched.append(target)

    # Save initial 60 catalogue (matched candidates only, preserving raw records)
    initial = {
        "format_version": "KA-IMPORT-1.0",
        "batch_type": "catalogue",
        "universe_id": "naruto",
        "generated_for": "initial_60_evaluation",
        "characters": matched_candidates,
        "unmatched_targets": unmatched,
        "stats": {
            "targets": len(TARGETS),
            "matched": len(matched_candidates),
            "unmatched": len(unmatched),
        },
    }
    Path("data/naruto_initial_60_catalogue.json").write_text(
        json.dumps(initial, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    Path("data/naruto_character_id_mapping.json").write_text(
        json.dumps({"targets": len(TARGETS), "mapping": mapping}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    # Image manifest
    image_manifest = []
    for candidate in matched_candidates:
        images = []
        for img in candidate.get("images", []):
            images.append({
                "url": img["url"],
                "status": img.get("status", "pending"),
                "format": img.get("format"),
                "width": img.get("width"),
                "height": img.get("height"),
                "sha256": img.get("sha256"),
                "bytes": img.get("bytes"),
            })
        image_manifest.append({
            "target_name": candidate["name"],
            "candidate_id": candidate["candidate_id"],
            "image_count": len(images),
            "images": images,
        })
    Path("data/naruto_initial_60_image_manifest.json").write_text(
        json.dumps({"characters": image_manifest}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print(f"Matched {len(matched_candidates)}/{len(TARGETS)}")
    if unmatched:
        print("Unmatched:", unmatched)


if __name__ == "__main__":
    main()
