"""Build a One Piece batch from a prepared roster and update cumulative artefacts.

Usage: python -X utf8 scripts/build_one_piece_batch.py --batch 2 --roster data/one_piece_batch_002_roster.json

Stage 01 only: research, catalogue, artwork and Claude assignment preparation.
No Power, Role Fit, rarity, score, approval or publication status is allocated.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import scripts.build_one_piece_batch_001 as base
from scripts.one_piece_quality import build_completeness_report

ROOT = Path("data")


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def merge_registry(
    records: list[dict[str, Any]], manifest: dict[str, Any], batch_id: str
) -> dict[str, Any]:
    registry_path = ROOT / "one_piece_master_registry.json"
    existing = (
        json.loads(registry_path.read_text(encoding="utf-8"))
        if registry_path.exists()
        else {
            "universe_id": "one_piece",
            "generated_at": base.utc_now(),
            "batches": [],
            "characters": [],
        }
    )
    by_id = {item["character_id"]: item for item in existing["characters"]}
    art_by_id = {item["candidate_id"]: item["status"] for item in manifest["images"]}
    for record in records:
        item = {
            "character_id": record["candidate_id"],
            "canonical_name": record["canonical_name"],
            "display_name": record["display_name"],
            "aliases": record["aliases"],
            "source_identifiers": {
                "fandom_pageid": record["source_metadata"].get("fandom_pageid"),
                "fandom_revision": record["source_metadata"].get("fandom_revision"),
                "source_url": record["source_url"],
            },
            "batch_membership": sorted(
                set(by_id.get(record["candidate_id"], {}).get("batch_membership", []))
                | {batch_id}
            ),
            "faction": record["faction"],
            "species": record["species"],
            "canonical_identity": "resolved",
            "research_status": record["research_gate"],
            "artwork_status": art_by_id.get(record["candidate_id"], "missing"),
            "evaluation_status": "not_started",
            "approval_status": "not_approved",
            "unresolved_identity_issues": [],
            "identity_mapping_note": (
                None
                if record["display_name"] == record["canonical_name"]
                else f"Display name maps to canonical Fandom title {record['canonical_name']}."
            ),
        }
        by_id[record["candidate_id"]] = item
    existing["generated_at"] = base.utc_now()
    existing["batches"] = sorted(set(existing["batches"]) | {batch_id})
    existing["characters"] = sorted(
        by_id.values(), key=lambda item: item["character_id"]
    )
    existing["character_count"] = len(existing["characters"])
    return existing


def build_cumulative_progress(research: dict[str, Any]) -> dict[str, Any]:
    research_files = sorted(ROOT.glob("one_piece_batch_*_research.json"))
    batches: list[dict[str, Any]] = []
    total_researched = 0
    total_ready = 0
    total_artwork = 0
    for path in research_files:
        data = json.loads(path.read_text(encoding="utf-8"))
        batch_id = data["batch_id"]
        manifest_path = ROOT / f"{batch_id.replace('-', '_')}_image_manifest.json"
        manifest = (
            json.loads(manifest_path.read_text(encoding="utf-8"))
            if manifest_path.exists()
            else {"summary": {"valid": 0}}
        )
        counts = Counter()
        registry = json.loads((ROOT / "one_piece_master_registry.json").read_text(encoding="utf-8"))
        for character in registry["characters"]:
            if batch_id in character["batch_membership"]:
                counts[character["research_status"]] += 1
        researched = sum(counts.values())
        ready = counts["RESEARCH_READY"]
        batches.append(
            {
                "batch_id": batch_id,
                "candidates_researched": researched,
                "research_ready": ready,
                "partial_research": counts["PARTIAL_RESEARCH"],
                "insufficient_evidence": counts["INSUFFICIENT_EVIDENCE"],
                "artwork_valid": manifest["summary"]["valid"],
                "evaluation_ready": ready,
                "approved": 0,
                "published": 0,
                "research_package": f"data/{path.name}",
                "catalogue": f"data/{batch_id.replace('-', '_')}_catalogue.json",
            }
        )
        total_researched += researched
        total_ready += ready
        total_artwork += manifest["summary"]["valid"]
    return {
        "universe_id": "one_piece",
        "generated_at": base.utc_now(),
        "batches_completed": len(batches),
        "batch_ids": [item["batch_id"] for item in batches],
        "totals": {
            "candidates_researched": total_researched,
            "research_ready": total_ready,
            "partial_research": sum(item["partial_research"] for item in batches),
            "insufficient_evidence": sum(item["insufficient_evidence"] for item in batches),
            "artwork_valid": total_artwork,
            "evaluation_ready": total_ready,
            "approved": 0,
            "published": 0,
        },
        "batches": batches,
        "remaining_expansion_opportunities": [
            "Continue with further batches using additional well-documented supporting characters.",
            "Revisit unresolved candidates as better inspected sources become available.",
            "Incorporate approved One Piece evaluations only after explicit approval.",
        ],
    }


def write_cumulative_gallery() -> None:
    cards = []
    for research_path in sorted(ROOT.glob("one_piece_batch_*_research.json")):
        research = json.loads(research_path.read_text(encoding="utf-8"))
        batch_id = research["batch_id"]
        manifest_path = ROOT / f"{batch_id.replace('-', '_')}_image_manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        image_by_id = {item["candidate_id"]: item for item in manifest["images"]}
        for record in research["candidates"]:
            image = image_by_id.get(record["candidate_id"], {})
            cards.append(
                {
                    "id": record["candidate_id"],
                    "name": record["name"],
                    "batch": batch_id,
                    "faction": record["faction"],
                    "status": record["research_gate"],
                    "artwork": image.get("status", "missing"),
                    "image": image.get("image_url") or "",
                    "source": record["source_url"],
                    "abilities": [
                        ability["name"] for ability in record["demonstrated_abilities"][:6]
                    ],
                }
            )
    payload = json.dumps(cards, ensure_ascii=False).replace("<", "\\u003c")
    text = base.write_gallery(research, manifest)
    # The helper embeds only the last batch; inject the cumulative dataset.
    start = text.index("const DATA = ") + len("const DATA = ")
    end = text.index(";\nconst grid", start)
    text = text[:start] + payload + text[end:]
    text = text.replace(
        "Research Gallery — Batch 001",
        "Research Gallery — All Prepared Batches",
    )
    write_text(ROOT / "one_piece_review_gallery.html", text)


MASTER_REPORT_TEMPLATE = """# One Piece Expansion Master Report

## 1. Universe identity

- Name: One Piece
- ID: `one_piece`
- Emoji: 🏴‍☠️
- Canonical policy: `ONE-PIECE-CANON-0.1`
- Manga cutoff: Chapter {cutoff}

## 2. Completed batches

{batch_summary}

## 3. Cumulative status

- Candidates investigated: {researched}
- Research-ready: {ready}
- Partial research: {partial}
- Insufficient evidence: {insufficient}
- Valid artwork: {artwork}
- Evaluation-ready packages: {ready}
- Approved: 0
- Published: 0

## 4. Unresolved candidates

Unresolved and incomplete candidates are preserved per batch in
`one_piece_batch_NNN_unresolved_candidates.json` and in the master registry.
They are excluded from evaluation packages until additional inspected evidence
is available.

## 5. Artwork

Artwork is technically validated separately from visual identity verification
and publication permission. Source-dependent rights require review before any
publication. Large image caches remain outside Git.

## 6. Evaluation readiness

Only RESEARCH_READY candidates enter Claude packages. No Power, Role Fit,
rarity, score, approval or publication status has been allocated. Once genuinely
approved One Piece evaluations exist, they may be incorporated into future
calibration packages without altering previously approved records.

## 7. Remaining opportunities

- Continue with later batches covering additional crews, Marines, Revolutionary
  Army, World Government, kingdoms, historical figures and specialists.
- Preserve role diversity, especially doctors, strategists, support characters
  and stealth specialists.
- Revisit unresolved candidates when better inspected sources are available.

## 8. Publication safeguard

One Piece is research-preparation only. It is not activated as a playable
production universe until an evaluated dataset is approved and published.
"""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch", type=int, required=True)
    parser.add_argument("--roster", required=True)
    parser.add_argument("--date", default=base.PREPARED_DATE)
    parser.add_argument("--min-ready", type=int, default=60)
    args = parser.parse_args()

    number = args.batch
    batch_id = f"one-piece-batch-{number:03d}"
    label = f"Batch {number:03d}"
    prefix = f"one_piece_batch_{number:03d}"

    base.BATCH_ID = batch_id
    base.BATCH_DIR_LABEL = label
    base.PREPARED_DATE = args.date
    base.ROSTER = Path(args.roster)

    roster = json.loads(Path(args.roster).read_text(encoding="utf-8"))["candidates"]
    records, image_sources = base.fetch_research(roster)
    gate_counts = Counter(record["research_gate"] for record in records)
    ready = [
        record for record in records if record["research_gate"] == "RESEARCH_READY"
    ]
    if len(ready) < args.min_ready:
        raise RuntimeError(
            f"Only {len(ready)} research-ready candidates; target {args.min_ready} not met."
        )

    manifest = base.build_image_manifest(records, image_sources)
    catalogue = base.build_catalogue(ready, manifest)
    catalogue.save(ROOT / f"{prefix}_catalogue.json")

    research = {
        "universe_id": "one_piece",
        "batch_id": batch_id,
        "batch_status": "research_ready_gated",
        "prepared_date": args.date,
        "stage": "01_continuous_research",
        "framework": base.FRAMEWORK,
        "canonical_policy": base.CANON_POLICY,
        "scoring_version": base.SCORING_VERSION,
        "manga_cutoff_chapter": base.MANGA_CUTOFF_CHAPTER,
        "candidate_count": len(ready),
        "research_gate_counts": dict(sorted(gate_counts.items())),
        "research_ready_count": len(ready),
        "unresolved_count": len(records) - len(ready),
        "notes": [
            "Only RESEARCH_READY candidates with substantive demonstrated abilities and traceable sources are included.",
            "No Power, Role Fit, rarity, score, approval or publication status is allocated.",
            "Sources are inspected secondary profiles; chapter references were extracted from page text but primary manga was not opened.",
            "Adaptation-only and non-canon sections were excluded during deterministic extraction.",
        ],
        "candidates": ready,
    }
    write_json(ROOT / f"{prefix}_research.json", research)
    write_json(ROOT / f"{prefix}_image_manifest.json", manifest)

    unresolved = base.build_unresolved(records)
    write_json(ROOT / f"{prefix}_unresolved_candidates.json", unresolved)

    catalogue_raw = json.loads((ROOT / f"{prefix}_catalogue.json").read_text(encoding="utf-8"))
    completeness = build_completeness_report(catalogue_raw, manifest, research, None)
    write_json(ROOT / f"{prefix}_completeness_report.json", completeness)

    registry = merge_registry(records, manifest, batch_id)
    write_json(ROOT / "one_piece_master_registry.json", registry)
    progress = build_cumulative_progress(research)
    write_json(ROOT / "one_piece_expansion_progress.json", progress)

    assignment = (
        base.build_assignment(ready)
        .replace("one_piece_batch_001_", f"{prefix}_")
        .replace("one-piece-batch-001", batch_id)
        .replace("Batch 001", label)
    )
    write_text(ROOT / f"{prefix}_claude_assignment.md", assignment)

    batch_report = base.build_batch_report(
        records, research, manifest, unresolved, completeness
    )
    write_text(
        Path("docs") / f"ONE_PIECE_{label.replace(' ', '_').upper()}_RESEARCH_REPORT.md",
        batch_report + "\n",
    )

    write_cumulative_gallery()

    totals = progress["totals"]
    batch_summary = "\n".join(
        f"- {item['batch_id']}: {item['research_ready']} research-ready candidates; "
        f"see `docs/{item['batch_id'].replace('-', '_').upper()}_RESEARCH_REPORT.md`."
        for item in progress["batches"]
    )
    write_text(
        Path("docs") / "ONE_PIECE_EXPANSION_MASTER_REPORT.md",
        MASTER_REPORT_TEMPLATE.format(
            cutoff=base.MANGA_CUTOFF_CHAPTER,
            batch_summary=batch_summary,
            researched=totals["candidates_researched"],
            ready=totals["research_ready"],
            partial=totals["partial_research"],
            insufficient=totals["insufficient_evidence"],
            artwork=totals["artwork_valid"],
        )
        + "\n",
    )

    print(
        json.dumps(
            {
                "batch_id": batch_id,
                "researched": len(records),
                "gate_counts": dict(gate_counts),
                "ready": len(ready),
                "unresolved": unresolved["candidate_count"],
                "artwork": manifest["summary"],
                "cumulative_ready": totals["research_ready"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
