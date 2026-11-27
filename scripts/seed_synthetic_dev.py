"""Seed an isolated synthetic dataset for local Telegram smoke testing.

Usage:
    set ARENA_DATASET_KIND=synthetic
    set ARENA_DB_PATH=data/dev_synthetic.sqlite3
    set ARENA_STATE_DB_PATH=data/dev_synthetic_state.sqlite3
    python -m scripts.seed_synthetic_dev
"""

from __future__ import annotations

import os
from pathlib import Path

from app.database import (
    CharacterDatabase,
    ImageMetadata,
    ImageValidationStatus,
    SpeciesKind,
)
from app.scoring import DatasetKind, SCORING_ROLES


def main() -> None:
    db_path = Path(os.getenv("ARENA_DB_PATH", "data/dev_synthetic.sqlite3"))
    db_path.parent.mkdir(parents=True, exist_ok=True)
    db = CharacterDatabase(db_path)

    try:
        try:
            db.get_universe("naruto")
        except Exception:
            db.create_universe(universe_id="naruto", name="Naruto (Synthetic Dev)", active=True)

        rarities = ["Common", "Uncommon", "Rare", "Epic", "Legendary"]
        for i in range(18):
            cid = f"syn_naruto_{i:02d}"
            fits = {
                role: ((i + idx) % 5) + 1
                for idx, role in enumerate(SCORING_ROLES)
            }
            try:
                db.get_character_entry(cid)
            except Exception:
                db.add_character(
                    character_id=cid,
                    universe_id="naruto",
                    name=f"Synthetic Shinobi {i:02d}",
                    species=SpeciesKind.HUMAN,
                    rarity=rarities[i % len(rarities)],
                    power=(i % 5) + 1,
                    fit=fits,
                    canonical_version="Dev Synthetic",
                    image=ImageMetadata(
                        url_or_ref="",
                        status=ImageValidationStatus.VERIFIED,
                    ),
                )
                db.submit_for_review(cid)
                db.approve_character(cid)

        db.publish_dataset(
            universe_id="naruto",
            dataset_version="naruto-syn-v1",
            kind=DatasetKind.SYNTHETIC,
        )
        print(f"Seeded isolated synthetic dataset 'naruto-syn-v1' into {db_path}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
