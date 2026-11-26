"""Dattebayo provider tests with controlled fixtures."""

from __future__ import annotations

from app.content.providers.dattebayo import DattebayoProvider, _fetch_json


def test_provider_maps_characters(monkeypatch) -> None:
    payload = {
        "total": 2,
        "currentPage": 1,
        "pageSize": 100,
        "characters": [
            {
                "id": 1,
                "name": "Naruto Uzumaki",
                "images": ["https://example.com/naruto.png"],
                "debut": {"manga": "Naruto Chapter #1", "anime": "Naruto Episode #1", "appearsIn": "Anime, Manga"},
                "personal": {"species": "Human", "classification": ["Jinchūriki"], "titles": ["fox"]},
            },
            {
                "id": 2,
                "name": "Boruto Uzumaki",
                "images": ["https://example.com/boruto.png"],
                "debut": {"manga": "Naruto Chapter #700", "anime": "Boruto Episode #1", "appearsIn": "Anime, Manga"},
                "personal": {"species": "Human", "classification": []},
            },
        ],
    }

    monkeypatch.setattr("app.content.providers.dattebayo._fetch_json", lambda url: payload)
    provider = DattebayoProvider()
    candidates = provider.collect()
    assert len(candidates) == 2
    assert candidates[0].name == "Naruto Uzumaki"
    assert candidates[0].universe == "Naruto"
    assert candidates[0].canonical_eligibility == "eligible"
    assert candidates[1].universe == "Boruto"
    assert "Boruto-era" in " ".join(candidates[1].notes)


def test_provider_flags_non_human_species(monkeypatch) -> None:
    payload = {
        "total": 1,
        "currentPage": 1,
        "pageSize": 100,
        "characters": [
            {
                "id": 3,
                "name": "Kurama",
                "images": [],
                "debut": {"manga": "Naruto Chapter #1", "anime": "Naruto Episode #1", "appearsIn": "Anime, Manga"},
                "personal": {"species": "Tailed Beast", "classification": []},
            }
        ],
    }
    monkeypatch.setattr("app.content.providers.dattebayo._fetch_json", lambda url: payload)
    provider = DattebayoProvider()
    candidates = provider.collect()
    assert candidates[0].canonical_eligibility == "uncertain"
    assert "Tailed Beast" in candidates[0].eligibility_reason
