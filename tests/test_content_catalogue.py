"""Deterministic catalogue deduplication and stats tests."""

from __future__ import annotations

from app.content.catalogue import deduplicate_candidates
from app.content.models import CandidateCharacter


def make_candidate(cid: str, name: str, universe: str = "Naruto", images=None) -> CandidateCharacter:
    return CandidateCharacter(
        candidate_id=cid,
        name=name,
        universe=universe,
        source="dattebayo",
        source_url="https://example.com",
        image_urls=images or [],
        canonical_eligibility="eligible",
    )


def test_deduplicate_by_candidate_id() -> None:
    a = make_candidate("d:1", "Naruto Uzumaki")
    b = make_candidate("d:1", "Naruto Uzumaki (Clone)")
    unique, duplicates = deduplicate_candidates([a, b])
    assert len(unique) == 1
    assert len(duplicates) == 1
    assert duplicates[0]["candidate_id"] == "d:1"


def test_deduplicate_by_normalized_name() -> None:
    a = make_candidate("d:1", "Sasuke Uchiha")
    b = make_candidate("d:2", "  sasuke   uchiha ")
    unique, duplicates = deduplicate_candidates([a, b])
    assert len(unique) == 1
    assert len(duplicates) == 1


def test_deduplicate_preserves_distinct_candidates() -> None:
    a = make_candidate("d:1", "Naruto Uzumaki")
    b = make_candidate("d:2", "Sasuke Uchiha")
    unique, duplicates = deduplicate_candidates([a, b])
    assert len(unique) == 2
    assert duplicates == []
