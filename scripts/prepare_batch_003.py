"""Prepare Naruto batch 003 catalogue, image manifest and KA-IMPORT export."""

from __future__ import annotations

import json
from pathlib import Path

TARGETS = [
    "Neji Hyuga", "Hinata Hyuga", "Ino Yamanaka", "Shino Aburame", "Kiba Inuzuka",
    "Choji Akimichi", "Tenten", "Asuma Sarutobi", "Kurenai Yuhi", "Shikaku Nara",
    "Inoichi Yamanaka", "Choza Akimichi", "Shizune", "Anko Mitarashi", "Iruka Umino",
    "Ebisu", "Konohamaru Sarutobi", "Yamato", "Sai", "Dan Kato", "Temari", "Kankuro",
    "Baki", "Rasa", "Pakura", "Hidan", "Zabuza Momochi", "Haku", "Karin",
    "Suigetsu Hozuki", "Jugo", "Kimimaro", "Jirobo", "Kidomaru", "Tayuya",
    "White Zetsu", "Omoi", "Karui", "Darui", "C (Hidden Cloud shinobi)", "Mabui",
    "Ao", "Chojuro", "Yugito Nii", "Yagura Karatachi", "Roshi", "Han", "Utakata",
    "Fu", "Rin Nohara",
]


def normalize(name: str) -> str:
    import unicodedata
    return unicodedata.normalize('NFKD', name).encode('ascii', 'ignore').decode().lower().strip()


def main() -> None:
    catalogue = json.loads(Path("data/naruto_candidates.json").read_text(encoding="utf-8"))
    by_norm = {normalize(c["name"]): c for c in catalogue["candidates"]}

    matched = []
    unmatched = []
    for t in TARGETS:
        c = by_norm.get(normalize(t))
        if c:
            matched.append(c)
        else:
            unmatched.append(t)

    # Build catalogue file
    out_catalogue = {
        "universe": "Naruto",
        "source": "dattebayo",
        "provider": "dattebayo",
        "generated_for": "batch_003",
        "stats": {
            "targets": len(TARGETS),
            "matched": len(matched),
            "unmatched": len(unmatched),
        },
        "unmatched": unmatched,
        "candidates": matched,
    }
    Path("data/naruto_batch_003_catalogue.json").write_text(
        json.dumps(out_catalogue, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    # Image manifest
    image_manifest = []
    for c in matched:
        images = []
        for img in c.get("images", []):
            images.append({
                "url": img["url"],
                "status": img.get("status", "pending"),
                "format": img.get("format"),
                "width": img.get("width"),
                "height": img.get("height"),
                "sha256": img.get("sha256"),
                "bytes": img.get("bytes"),
                "source": img.get("source"),
            })
        image_manifest.append({
            "name": c["name"],
            "candidate_id": c["candidate_id"],
            "image_count": len(images),
            "valid_count": sum(1 for i in images if i["status"] == "valid"),
            "images": images,
        })
    Path("data/naruto_batch_003_image_manifest.json").write_text(
        json.dumps({"characters": image_manifest}, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    # KA-IMPORT export
    from app.content.models import CandidateCatalogue, CandidateCharacter, CandidateImage
    from app.content.export import save_export
    from datetime import datetime, timezone

    candidates = []
    for c in matched:
        images = [CandidateImage(**img) for img in c.get("images", [])]
        candidates.append(CandidateCharacter(
            candidate_id=c["candidate_id"],
            name=c["name"],
            universe=c["universe"],
            source=c["source"],
            source_url=c["source_url"],
            aliases=c.get("aliases", []),
            image_urls=c.get("image_urls", []),
            images=images,
            debut=c.get("debut", {}),
            classification=c.get("classification", []),
            species=c.get("species"),
            canonical_eligibility=c.get("canonical_eligibility", "uncertain"),
            eligibility_reason=c.get("eligibility_reason", ""),
            source_metadata=c.get("source_metadata", {}),
            review_status=c.get("review_status", "pending"),
            notes=c.get("notes", []),
        ))
    cat = CandidateCatalogue(
        universe="Naruto",
        source="dattebayo",
        provider="dattebayo",
        generated_at=datetime.now(timezone.utc).isoformat(),
        candidates=candidates,
    )
    save_export(cat, Path("data/naruto_batch_003_ka_import.json"), universe_id="naruto")

    print(f"Matched {len(matched)}/{len(TARGETS)}")
    if unmatched:
        print("Unmatched:", unmatched)


if __name__ == "__main__":
    main()
