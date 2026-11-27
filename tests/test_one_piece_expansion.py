"""Focused tests for continuous One Piece batch expansion."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.one_piece_quality import research_ready_valid  # noqa: E402

ROOT = Path("data")


def load(name: str):
    return json.loads((ROOT / name).read_text(encoding="utf-8"))


def test_batch_002_research_gate() -> None:
    research = load("one_piece_batch_002_research.json")
    catalogue = load("one_piece_batch_002_catalogue.json")
    unresolved = load("one_piece_batch_002_unresolved_candidates.json")
    registry = load("one_piece_master_registry.json")
    research_ids = {item["candidate_id"] for item in research["candidates"]}
    catalogue_ids = {item["candidate_id"] for item in catalogue["candidates"]}
    unresolved_ids = {item["candidate_id"] for item in unresolved["candidates"]}
    registry_ids = {item["character_id"] for item in registry["characters"]}
    assert research_ids == catalogue_ids
    assert not research_ids & unresolved_ids
    assert research_ids <= registry_ids
    assert 60 <= len(research_ids) <= 100
    for record in research["candidates"]:
        assert research_ready_valid(record)[0] is True
        assert record["supporting_evidence"]
        assert record["demonstrated_abilities"]


def test_batch_003_research_gate() -> None:
    research = load("one_piece_batch_003_research.json")
    catalogue = load("one_piece_batch_003_catalogue.json")
    unresolved = load("one_piece_batch_003_unresolved_candidates.json")
    research_ids = {item["candidate_id"] for item in research["candidates"]}
    assert research_ids == {item["candidate_id"] for item in catalogue["candidates"]}
    assert not research_ids & {
        item["candidate_id"] for item in unresolved["candidates"]
    }
    assert len(research_ids) >= 30
    for record in research["candidates"]:
        assert research_ready_valid(record)[0] is True


def test_batch_001_and_002_do_not_duplicate_identities() -> None:
    first = {item["candidate_id"] for item in load("one_piece_batch_001_research.json")["candidates"]}
    second = {item["candidate_id"] for item in load("one_piece_batch_002_research.json")["candidates"]}
    third = {item["candidate_id"] for item in load("one_piece_batch_003_research.json")["candidates"]}
    assert not first & second
    assert not first & third
    assert not second & third


def test_cumulative_registry_and_progress() -> None:
    registry = load("one_piece_master_registry.json")
    progress = load("one_piece_expansion_progress.json")
    ready_total = sum(
        len(load(f"{batch_id.replace('-', '_')}_research.json")["candidates"])
        for batch_id in progress["batch_ids"]
    )
    assert progress["batches_completed"] == len(progress["batch_ids"]) >= 3
    assert "one-piece-batch-001" in progress["batch_ids"]
    assert "one-piece-batch-003" in progress["batch_ids"]
    assert progress["totals"]["research_ready"] == ready_total
    assert registry["character_count"] == len(registry["characters"])
    assert registry["character_count"] >= progress["totals"]["research_ready"]
    assert progress["totals"]["approved"] == 0
    assert progress["totals"]["published"] == 0


def test_batch_002_assignment_is_self_contained() -> None:
    assignment = (
        ROOT / "one_piece_batch_002_claude_assignment.md"
    ).read_text(encoding="utf-8")
    for required in (
        "Batch 002",
        "one-piece-batch-002",
        "one_piece_batch_002_research.json",
        "ONE-PIECE-CANON-0.1",
        "EVAL-FRAMEWORK-1.0",
        '"captain"',
        '"healer"',
        "Ready-to-use prompt",
    ):
        assert required in assignment


def test_gallery_includes_all_prepared_batches() -> None:
    gallery = (ROOT / "one_piece_review_gallery.html").read_text(encoding="utf-8")
    assert "one-piece-batch-001" in gallery
    assert "one-piece-batch-002" in gallery
    assert "one-piece-batch-003" in gallery
    assert "All Prepared Batches" in gallery
    assert "Research review only" in gallery


def test_master_report_reflects_all_batches() -> None:
    report = (Path("docs") / "ONE_PIECE_EXPANSION_MASTER_REPORT.md").read_text(
        encoding="utf-8"
    )
    assert "one-piece-batch-001" in report
    assert "one-piece-batch-002" in report
    assert "one-piece-batch-003" in report
    assert "- Approved: 0" in report
    assert "- Published: 0" in report
