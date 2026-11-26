"""Tests for the Naruto 60-character reconciliation helpers."""

from __future__ import annotations

import json
from pathlib import Path

from app.content.export import export_catalogue_batch
from app.content.models import CandidateCatalogue, CandidateCharacter, CandidateImage


def test_id_mapping_has_60_entries() -> None:
    mapping = json.loads(Path("data/naruto_character_id_mapping.json").read_text(encoding="utf-8"))
    assert mapping["targets"] == 60
    assert len(mapping["mapping"]) == 60
    matched = [m for m in mapping["mapping"] if m["status"] == "matched"]
    assert len(matched) == 60


def test_initial_60_export_is_ka_import_compatible() -> None:
    payload = json.loads(Path("data/naruto_initial_60_ka_import.json").read_text(encoding="utf-8"))
    assert payload["format_version"] == "KA-IMPORT-1.0"
    assert payload["batch_type"] == "catalogue"
    assert payload["universe_id"] == "naruto"
    assert len(payload["characters"]) == 60
    for entry in payload["characters"]:
        assert entry["rarity"] == "Common"
        assert entry["power"] is None
        assert entry["status"] if "status" in entry else True


def test_curated_candidates_groups_exist() -> None:
    data = json.loads(Path("data/naruto_curated_candidates.json").read_text(encoding="utf-8"))
    assert data["total_naruto_candidates"] == 1159
    assert "ready_for_evaluation" in data["groups"]
    assert sum(data["stats"].values()) == 1159


def test_evaluated_dataset_has_60_records() -> None:
    data = json.loads(Path("data/naruto_evaluated_60_dataset.json").read_text(encoding="utf-8"))
    assert data["record_count"] == 60
    assert data["held_count"] == 7
    assert data["status"] == "draft"
    assert "rarity_distribution" in data
    assert sum(data["rarity_distribution"].values()) == 60


def test_evaluated_records_have_scores_and_rarity() -> None:
    data = json.loads(Path("data/naruto_evaluated_60_dataset.json").read_text(encoding="utf-8"))
    for rec in data["characters"]:
        assert 1 <= rec["power"] <= 5
        assert set(rec["fit"].keys()) == {"captain", "strategist", "attacker", "tank", "assassin", "support", "healer"}
        assert set(rec["scores"].keys()) == {"captain", "strategist", "attacker", "tank", "assassin", "support", "healer"}
        assert rec["rarity"] in {"Common", "Uncommon", "Rare", "Epic", "Legendary"}
        assert rec["held"] == (rec["evaluation_status"] == "held")
