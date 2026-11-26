"""KA-IMPORT-1.0 export tests."""

from __future__ import annotations

import json
from pathlib import Path

from app.content.export import export_catalogue_batch, IMPORT_FORMAT_VERSION
from app.content.models import CandidateCatalogue, CandidateCharacter, CandidateImage


def test_export_shape() -> None:
    candidate = CandidateCharacter(
        candidate_id="dattebayo:1",
        name="Naruto Uzumaki",
        universe="Naruto",
        source="dattebayo",
        source_url="https://example.com",
        aliases=["Seventh Hokage"],
        image_urls=["https://example.com/naruto.png"],
        images=[CandidateImage(url="https://example.com/naruto.png", sha256="abc", width=10, height=10, format="png", status="valid")],
        species="Human",
        canonical_eligibility="eligible",
        debut={"manga": "Naruto Chapter #1"},
    )
    catalogue = CandidateCatalogue(
        universe="Naruto",
        source="dattebayo",
        provider="dattebayo",
        generated_at="2026-01-01T00:00:00+00:00",
        candidates=[candidate],
    )
    payload = export_catalogue_batch(catalogue, universe_id="naruto")
    assert payload["format_version"] == IMPORT_FORMAT_VERSION
    assert payload["batch_type"] == "catalogue"
    assert payload["universe_id"] == "naruto"
    entry = payload["characters"][0]
    assert entry["character_id"] == "dattebayo_1"
    assert entry["name"] == "Naruto Uzumaki"
    assert entry["rarity"] == "Common"
    assert entry["species"] == "human"
    assert entry["canonical_version"] == "Naruto Chapter #1"
    assert entry["image"]["status"] == "pending"
    assert entry["image"]["checksum"] == "sha256-abc"
    assert entry["power"] is None
