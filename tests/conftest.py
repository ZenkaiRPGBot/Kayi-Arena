"""Shared fictional fixtures and helpers for Module 1 tests."""

from __future__ import annotations

from app.engine import CatalogEntry

DEFAULT_WEIGHTS: dict[str, float] = {
    "Mythic": 5.0,
    "Legendary": 15.0,
    "Epic": 25.0,
    "Rare": 30.0,
    "Common": 25.0,
}


def make_catalog(size: int = 20) -> tuple[CatalogEntry, ...]:
    rarities = ("Mythic", "Legendary", "Epic", "Rare", "Common")
    return tuple(
        CatalogEntry(character_id=f"char_{i:03d}", rarity_id=rarities[i % len(rarities)])
        for i in range(size)
    )
