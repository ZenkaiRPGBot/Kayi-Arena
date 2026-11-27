"""Diagnostic: map every evaluation name to a catalogue candidate."""

from __future__ import annotations

import json
import unicodedata
from collections import Counter
from pathlib import Path

CATALOGUE = Path("data/naruto_candidates.json")
BATCHES = [
    ("003", "data/naruto_batch_003_evaluations_revised.json"),
    ("004-A", "data/naruto_batch_004_a_evaluations.json"),
    ("004-B", "data/naruto_batch_004_b_evaluations.json"),
]

ALIASES = {
    "C (Kumogakure shinobi)": "C",
    "Reto — First Kazekage": "Reto",
    "Shamon — Second Kazekage": "Shamon",
    "Byakuren — First Mizukage": "Byakuren",
    "Ishikawa — First Tsuchikage": "Ishikawa",
    "A — First Raikage": "A (First Raikage)",
    "A — Second Raikage": "A (Second Raikage)",
    "Kiri — Allied Shinobi Forces": "Kiri (ninja)",
    "Hoheto Hyuga": "Hoheto Hyūga",
    "Yoroi Akado": "Yoroi Akadō",
    "Chukichi": "Chūkichi",
    "Kakko": "Kakkō",
    "Choji Akimichi": "Chōji Akimichi",
    "Chojuro": "Chōjūrō",
    "Nono Yakushi": "Nonō Yakushi",
}


def norm(value: str) -> str:
    return unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode().lower().strip()


def main() -> None:
    catalogue = json.loads(CATALOGUE.read_text(encoding="utf-8"))
    by_norm = {norm(c["name"]): c for c in catalogue["candidates"]}

    seen: dict[str, str] = {}
    unmatched = []
    matched = 0
    total = 0
    for batch, path in BATCHES:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        for entry in data["characters"]:
            total += 1
            name = entry["name"]
            target = ALIASES.get(name, name)
            candidate = by_norm.get(norm(target))
            if candidate is None:
                unmatched.append((batch, name))
                continue
            matched += 1
            cid = candidate["candidate_id"]
            if cid in seen:
                print(f"DUPLICATE {cid}: {seen[cid]} and {batch}/{name}")
            seen[cid] = f"{batch}/{name}"

    print(f"total={total} matched={matched} unmatched={len(unmatched)} unique_ids={len(seen)}")
    for batch, name in unmatched:
        print(f"  UNMATCHED {batch}: {name!r}")

    # Catalogue image coverage for matched candidates.  Prefer the validated
    # consolidated catalogue when it exists; the raw scrape still carries stale
    # statuses for the ten URLs that were fixed from .png to .PNG.
    validated = Path("data/naruto_expansion_003_004_catalogue.json")
    image_source = validated if validated.exists() else CATALOGUE
    image_catalogue = json.loads(image_source.read_text(encoding="utf-8"))
    images_by_id = {c["candidate_id"]: c.get("images", []) for c in image_catalogue["candidates"]}
    status = Counter()
    for cid in seen:
        imgs = images_by_id.get(cid, [])
        if any(i.get("status") == "valid" for i in imgs):
            status["valid"] += 1
        elif imgs:
            status["invalid"] += 1
        else:
            status["missing"] += 1
    print(f"image coverage ({image_source.name}):", dict(status))


if __name__ == "__main__":
    main()
