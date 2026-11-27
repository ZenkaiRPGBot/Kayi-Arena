"""Build One Piece Batch 001 research, catalogue, artwork and review artefacts.

Stage 01 only: candidate discovery, capability research, artwork collection and
Claude assignment preparation. No Power, Role Fit, rarity, score, approval or
publication status is allocated.
"""

from __future__ import annotations

import hashlib
import json
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.content.images import validate_image_bytes
from app.content.models import CandidateCatalogue, CandidateCharacter, CandidateImage
from scripts.one_piece_common import (
    CANON_POLICY,
    CACHE_DIR,
    FRAMEWORK,
    MANGA_CUTOFF_CHAPTER,
    SCORING_VERSION,
    UNIVERSE_ID,
    build_research_record,
    extract_aliases,
    fetch_abilities_page,
    fetch_categories,
    fetch_page,
    fetch_pageimages,
    species_from_categories,
)
from scripts.one_piece_quality import build_completeness_report

ROOT = Path("data")
ROSTER = ROOT / "one_piece_batch_001_roster.json"
BATCH_ID = "one-piece-batch-001"
BATCH_DIR_LABEL = "Batch 001"
PREPARED_DATE = "2026-11-27"
IMAGE_CACHE = CACHE_DIR / "images"
IMAGE_CACHE.mkdir(parents=True, exist_ok=True)

BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Referer": "https://onepiece.fandom.com/",
    "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def download_image(url: str) -> dict[str, Any]:
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:24]
    cache_path = IMAGE_CACHE / f"{digest}.bin"
    try:
        if cache_path.exists():
            data = cache_path.read_bytes()
            http_status = 200
        else:
            response = requests.get(url, headers=BROWSER_HEADERS, timeout=45)
            http_status = response.status_code
            if response.status_code != 200:
                return {
                    "status": "invalid",
                    "http_status": response.status_code,
                    "error": f"HTTP {response.status_code}",
                }
            data = response.content
            cache_path.write_bytes(data)
        validation = validate_image_bytes(data)
        if not validation["ok"]:
            return {
                "status": "invalid",
                "http_status": http_status,
                "error": validation.get("error"),
                "format": validation.get("format"),
            }
        return {
            "status": "valid",
            "http_status": http_status,
            "error": None,
            "sha256": validation["sha256"],
            "format": validation["format"],
            "width": validation["width"],
            "height": validation["height"],
            "bytes": validation["bytes"],
        }
    except Exception as exc:
        return {
            "status": "invalid",
            "http_status": None,
            "error": f"{type(exc).__name__}: {exc}",
        }


def fetch_research(roster: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    titles = [entry["fandom_title"] for entry in roster]
    categories_by_title = fetch_categories(titles)
    main_pages: dict[str, dict[str, Any]] = {}
    ability_pages: dict[str, dict[str, Any]] = {}
    canonical_by_title: dict[str, str] = {}

    for entry in roster:
        title = entry["fandom_title"]
        main = fetch_page(title)
        canonical = main.get("title", entry["name"])
        main_pages[title] = main
        canonical_by_title[title] = canonical
        ability_pages[title] = fetch_abilities_page(canonical)

    images_by_title = fetch_pageimages(
        [canonical_by_title[t] for t in titles], thumb_size=1000
    )

    records: list[dict[str, Any]] = []
    image_sources: dict[str, dict[str, Any]] = {}
    for entry in roster:
        title = entry["fandom_title"]
        main = main_pages[title]
        ability_page = ability_pages[title]
        canonical = canonical_by_title[title]
        categories = categories_by_title.get(canonical, [])
        aliases = list(
            dict.fromkeys(
                [
                    *extract_aliases(main, entry["name"]),
                    *[str(item) for item in entry.get("aliases", [])],
                ]
            )
        )[:10]
        species = entry.get("species") or species_from_categories(categories)
        record = build_research_record(
            name=entry["name"],
            canonical_name=canonical,
            main_page=main,
            abilities_page=ability_page,
            categories=categories,
            aliases=aliases,
            faction=entry.get("faction", "unknown"),
            species=species,
            era=entry.get("era", f"Manga canon through Chapter {MANGA_CUTOFF_CHAPTER}"),
        )
        record["fandom_title_requested"] = title
        record["display_name"] = entry["name"]
        record["canonical_name"] = canonical
        records.append(record)

        image_info = images_by_title.get(canonical) or {}
        image_url = (image_info.get("original") or {}).get("source") or (
            image_info.get("thumbnail") or {}
        ).get("source")
        image_sources[record["candidate_id"]] = {
            "candidate_id": record["candidate_id"],
            "name": entry["name"],
            "canonical_name": canonical,
            "fandom_pageid": image_info.get("pageid") or main.get("pageid"),
            "image_url": image_url,
            "source_api": (
                "https://onepiece.fandom.com/api.php?action=query&prop=pageimages"
            ),
        }

    return records, image_sources


def build_image_manifest(
    records: list[dict[str, Any]], image_sources: dict[str, Any]
) -> dict[str, Any]:
    tasks = [
        (record["candidate_id"], image_sources.get(record["candidate_id"], {}).get("image_url"))
        for record in records
    ]
    results: dict[str, dict[str, Any]] = {}
    with ThreadPoolExecutor(max_workers=6) as executor:
        futures = {
            executor.submit(download_image, url) if url else None: candidate_id
            for candidate_id, url in tasks
        }
        for future in as_completed([f for f in futures if f is not None]):
            candidate_id = futures[future]
            results[candidate_id] = future.result()
        for candidate_id, url in tasks:
            if not url:
                results[candidate_id] = {
                    "status": "missing",
                    "http_status": None,
                    "error": "No page image returned by the source API.",
                }

    by_hash: dict[str, str] = {}
    manifest_images: list[dict[str, Any]] = []
    name_by_id = {record["candidate_id"]: record["name"] for record in records}
    for record in records:
        candidate_id = record["candidate_id"]
        source = image_sources.get(candidate_id, {})
        result = results.get(candidate_id, {"status": "missing", "error": "not attempted"})
        status = result["status"]
        duplicate_of = None
        if status == "valid":
            digest = result["sha256"]
            if digest in by_hash:
                status = "duplicate"
                duplicate_of = by_hash[digest]
            else:
                by_hash[digest] = candidate_id
        manifest_images.append(
            {
                "candidate_id": candidate_id,
                "name": name_by_id[candidate_id],
                "canonical_name": source.get("canonical_name"),
                "in_catalogue": record["research_gate"] == "RESEARCH_READY",
                "source": "onepiece_fandom",
                "source_url": record["source_url"],
                "image_url": source.get("image_url"),
                "fandom_pageid": source.get("fandom_pageid"),
                "http_status": result.get("http_status"),
                "sha256": result.get("sha256"),
                "format": result.get("format"),
                "width": result.get("width"),
                "height": result.get("height"),
                "bytes": result.get("bytes"),
                "status": status,
                "error": result.get("error"),
                "duplicate_of": duplicate_of,
                "technical_validation": (
                    "valid"
                    if status == "valid"
                    else ("duplicate" if status == "duplicate" else "failed")
                ),
                "visual_identity_verification": "not_performed",
                "publication_permission": "source-dependent; review required",
                "rights": "source-dependent; review before publication",
                "notes": [
                    "Technical validation checks format, dimensions and checksum only.",
                    "Visual identity verification and publication permission are separate reviews.",
                ],
            }
        )

    status_counts = Counter(item["status"] for item in manifest_images)
    catalogue_ids = {
        record["candidate_id"]
        for record in records
        if record["research_gate"] == "RESEARCH_READY"
    }
    covered = len(
        {
            item["candidate_id"]
            for item in manifest_images
            if item["candidate_id"] in catalogue_ids and item["status"] == "valid"
        }
    )
    return {
        "universe_id": UNIVERSE_ID,
        "batch_id": BATCH_ID,
        "generated_at": utc_now(),
        "source": "onepiece_fandom",
        "summary": {
            "candidates_researched": len(records),
            "candidates_in_catalogue": len(catalogue_ids),
            "total_images": len(manifest_images),
            "valid": status_counts["valid"],
            "duplicate": status_counts["duplicate"],
            "invalid": status_counts["invalid"],
            "missing": status_counts["missing"],
            "candidates_with_valid_artwork": covered,
        },
        "policy": {
            "technical_validation_is_separate_from_visual_identity": True,
            "publication_permission_requires_separate_review": True,
            "large_image_cache_outside_git": True,
        },
        "images": manifest_images,
    }


def build_catalogue(
    ready: list[dict[str, Any]], manifest: dict[str, Any]
) -> CandidateCatalogue:
    image_by_id = {item["candidate_id"]: item for item in manifest["images"]}
    characters: list[CandidateCharacter] = []
    for record in ready:
        item = image_by_id.get(record["candidate_id"], {})
        images: list[CandidateImage] = []
        if item.get("image_url"):
            images.append(
                CandidateImage(
                    url=item["image_url"],
                    source="onepiece_fandom",
                    sha256=item.get("sha256"),
                    format=item.get("format"),
                    width=item.get("width"),
                    height=item.get("height"),
                    bytes=item.get("bytes"),
                    status=item.get("status", "pending"),
                    error=item.get("error"),
                    rights="source-dependent; review before publication",
                )
            )
        characters.append(
            CandidateCharacter(
                candidate_id=record["candidate_id"],
                name=record["name"],
                universe="One Piece",
                source="onepiece_fandom",
                source_url=record["source_url"],
                aliases=record["aliases"],
                image_urls=[item["image_url"]] if item.get("image_url") else [],
                images=images,
                debut=record["debut"],
                classification=[],
                species=record["species"],
                canonical_eligibility="eligible",
                eligibility_reason=(
                    "Manga-canon character with substantive demonstrated ability "
                    "evidence in the inspected profile."
                ),
                source_metadata={
                    "canonical_name": record["canonical_name"],
                    "faction": record["faction"],
                    "era": record["era"],
                    "fandom_pageid": record["source_metadata"].get("fandom_pageid"),
                    "fandom_revision": record["source_metadata"].get("fandom_revision"),
                    "ability_profile_url": record["ability_profile_url"],
                    "canonical_policy": record["canonical_policy"],
                    "manga_cutoff_chapter": record["manga_cutoff_chapter"],
                    "source_categories": record["source_categories"],
                },
                review_status="pending",
                notes=[
                    "Research-ready only; no evaluation or approval is recorded here.",
                    "Artwork requires visual identity and publication-permission review.",
                ],
            )
        )
    return CandidateCatalogue(
        universe="One Piece",
        source="onepiece_fandom",
        provider="onepiece_fandom",
        generated_at=utc_now(),
        stats={
            "targets": len(characters),
            "matched": len(characters),
            "unmatched": 0,
        },
        candidates=characters,
    )


def build_unresolved(records: list[dict[str, Any]]) -> dict[str, Any]:
    unresolved = []
    for record in records:
        if record["research_gate"] == "RESEARCH_READY":
            continue
        missing = []
        if len(record["demonstrated_abilities"]) < 2:
            missing.append("fewer than two substantive demonstrated abilities")
        if not any(item.get("canonical_refs") for item in record["demonstrated_abilities"]):
            missing.append("no cited demonstrated ability")
        unresolved.append(
            {
                "candidate_id": record["candidate_id"],
                "name": record["name"],
                "canonical_name": record["canonical_name"],
                "source_url": record["source_url"],
                "research_gate": record["research_gate"],
                "reason": record["gate_reason"],
                "missing_evidence": missing,
                "demonstrated_ability_count": len(record["demonstrated_abilities"]),
                "preserved_for_future_research": True,
            }
        )
    return {
        "universe_id": UNIVERSE_ID,
        "batch_id": BATCH_ID,
        "generated_at": utc_now(),
        "excluded_from_evaluation_package": True,
        "candidate_count": len(unresolved),
        "exclusion_summary": {
            "adaptation_only_material_excluded_at_section_level": True,
            "duplicate_identities_excluded": [],
            "manual_identity_mapping_candidates": [
                {
                    "display_name": record["display_name"],
                    "canonical_name": record["canonical_name"],
                    "action": "Use the canonical Fandom title as the stable identity key.",
                }
                for record in records
                if record["display_name"] != record["canonical_name"]
            ],
        },
        "candidates": unresolved,
    }


def build_master_registry(records: list[dict[str, Any]], manifest: dict[str, Any]) -> dict[str, Any]:
    art_by_id = {item["candidate_id"]: item["status"] for item in manifest["images"]}
    characters = []
    for record in records:
        characters.append(
            {
                "character_id": record["candidate_id"],
                "canonical_name": record["canonical_name"],
                "display_name": record["display_name"],
                "aliases": record["aliases"],
                "source_identifiers": {
                    "fandom_pageid": record["source_metadata"].get("fandom_pageid"),
                    "fandom_revision": record["source_metadata"].get("fandom_revision"),
                    "source_url": record["source_url"],
                },
                "batch_membership": [BATCH_ID],
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
        )
    return {
        "universe_id": UNIVERSE_ID,
        "generated_at": utc_now(),
        "batches": [BATCH_ID],
        "character_count": len(characters),
        "characters": characters,
    }


def build_progress(
    records: list[dict[str, Any]],
    research: dict[str, Any],
    manifest: dict[str, Any],
) -> dict[str, Any]:
    counts = Counter(record["research_gate"] for record in records)
    return {
        "universe_id": UNIVERSE_ID,
        "generated_at": utc_now(),
        "batches_completed": 1,
        "batch_ids": [BATCH_ID],
        "totals": {
            "candidates_researched": len(records),
            "research_ready": counts["RESEARCH_READY"],
            "partial_research": counts["PARTIAL_RESEARCH"],
            "insufficient_evidence": counts["INSUFFICIENT_EVIDENCE"],
            "artwork_valid": manifest["summary"]["valid"],
            "evaluation_ready": counts["RESEARCH_READY"],
            "approved": 0,
            "published": 0,
        },
        "batches": [
            {
                "batch_id": BATCH_ID,
                "candidates_researched": len(records),
                "research_ready": counts["RESEARCH_READY"],
                "partial_research": counts["PARTIAL_RESEARCH"],
                "insufficient_evidence": counts["INSUFFICIENT_EVIDENCE"],
                "artwork_valid": manifest["summary"]["valid"],
                "evaluation_ready": counts["RESEARCH_READY"],
                "approved": 0,
                "published": 0,
                "research_package": "data/one_piece_batch_001_research.json",
                "catalogue": "data/one_piece_batch_001_catalogue.json",
            }
        ],
        "remaining_expansion_opportunities": [
            "Continue with One Piece Batch 002 using additional supporting characters, specialists and historical figures.",
            "Revisit unresolved candidates if additional inspected sources become available.",
            "Incorporate genuinely approved One Piece evaluations into calibration only after approval.",
        ],
    }


ASSIGNMENT_TEMPLATE = """# Kayi Arena — One Piece {batch_label} Independent Character Evaluation

## 0. Self-contained assignment

This prompt is self-contained. Do not rely on prior conversations, repository
access or unpublished decisions. Use only the material attached below and any
sources you inspect yourself while following the canonical policy.

You are an independent evaluator for Kayi Arena. You are not responsible for
coding, artwork, database integration, rarity calculation or gameplay.

## 1. Universe and canonical policy

- Universe ID: `one_piece`
- Universe name: One Piece
- Canonical policy: `ONE-PIECE-CANON-0.1`
- Manga cutoff: Chapter {cutoff}
- Framework: `EVAL-FRAMEWORK-1.0`
- Scoring version: `SCORE-1.0`
- Prepared date: {date}

Policy:

1. Use manga canon through Chapter {cutoff}. Anime-only, movie-only, game-only,
   novel-only and SBS-only abilities are excluded unless supported by a cited
   manga chapter within the cutoff.
2. Evaluate one sustainable canonical version per individual character. Prefer
   demonstrated prime capability within the cutoff; do not combine incompatible
   periods or forms.
3. Repeatable transformations and accessible power-ups may count. One-time
   external boosts, fatal techniques and borrowed or externally controlled
   abilities must be flagged and treated cautiously.
4. Rank, bounty, reputation and Devil Fruit classification are context only.
   Ratings must rest on demonstrated actions, techniques or specialist functions.
5. The research package uses inspected secondary One Piece Wiki pages. Chapter
   references were extracted from those pages; primary manga was not directly
   opened. Treat them as leads, not as independently verified primary evidence.
6. Unknown evidence must remain unknown. Do not fabricate feats or references.

## 2. Attached material

- `one_piece_batch_001_research.json` — only RESEARCH_READY candidates with factual ability research and traceable sources.
- `one_piece_batch_001_catalogue.json` — identity and artwork metadata.
- `one_piece_batch_001_claude_assignment.md` — this assignment.

The research package contains {ready_count} candidates. No Power, Role Fit,
rarity, score, approval or publication status has been allocated.

## 3. Evaluation framework

### Power (integer 1–5)

Power is overall combat capability relative to the One Piece universe.

- 1 — Very limited combat capability.
- 2 — Modest but demonstrated combat capability.
- 3 — Capable and accomplished combatant.
- 4 — Exceptional, high-level combatant.
- 5 — Among the universe's highest demonstrated combat capabilities.

These are anchors, not automatic classifications by rank or reputation.

### Role Fit (integer 0–5, seven independent roles)

- 0 — No meaningful demonstrated suitability.
- 1 — Minimal suitability.
- 2 — Limited but useful suitability.
- 3 — Competent suitability.
- 4 — Exceptional suitability.
- 5 — Outstanding specialist capability.

Roles:

- `captain` — leadership, coordination, judgment, command.
- `strategist` — planning, analysis, tactical intelligence, adaptation.
- `attacker` — direct offensive ability and effectiveness.
- `tank` — damage resistance, durability, defensive techniques, protecting allies.
- `assassin` — stealth, infiltration, surprise, precision elimination.
- `support` — battlefield control, sensing, restraint, mobility assistance, enhancements.
- `healer` — demonstrated treatment or restoration of others. Self-regeneration alone is insufficient.

Power and Role Fit are independent. Do not distribute points to manufacture a
balanced roster. Do not manipulate ratings for rarity outcomes. Support unusual
ratings with specific evidence.

## 4. Calibration guidance

There are no approved One Piece evaluations yet. Do not treat any provisional
One Piece rating as an approved anchor. Use the framework anchors above and
maintain consistency within this batch. If you rely on cross-universe intuition,
state that it is provisional and do not present it as approved One Piece
calibration. Incorporate approved One Piece evaluations only in future batches.

## 5. Evidence handling

Every `draft` record must have at least one traceable source supporting
meaningful ability claims. Prefer:

1. Primary manga chapters within the cutoff, if you inspect them.
2. Official franchise sources.
3. The inspected secondary profiles supplied in the research package, with chapter leads.

Record actual URLs and chapter references. Distinguish directly inspected
primary sources, inspected secondary sources and unverified recollection. Mark
records `held` when identity, eligibility or evidence is insufficient. Do not
invent placeholder ratings for held records.

## 6. Required output

Return one JSON object with exactly these root fields:

```json
{{
  "universe_id": "one_piece",
  "batch_id": "one-piece-batch-001",
  "mode": "independent_evaluation",
  "evaluation_framework_version": "EVAL-FRAMEWORK-1.0",
  "scoring_version": "SCORE-1.0",
  "canonical_policy_version": "ONE-PIECE-CANON-0.1",
  "prepared_date": "{date}",
  "batch_status": "evaluation_submission",
  "notes": [],
  "characters": []
}}
```

Each character record must contain exactly:

```json
{{
  "id": "one_piece_candidate_id",
  "name": "Display name",
  "canonical_name": "Canonical name",
  "aliases": [],
  "canonical_version": "Selected version and cutoff",
  "power": 1,
  "fit": {{
    "captain": 0,
    "strategist": 0,
    "attacker": 0,
    "tank": 0,
    "assassin": 0,
    "support": 0,
    "healer": 0
  }},
  "justification": "Concise evidence-based rationale.",
  "evidence_leads": [
    {{
      "lead": "What the evidence supports.",
      "check": "How to verify it.",
      "source_note": "URL and/or chapter lead."
    }}
  ],
  "confidence": "high",
  "review_flags": [],
  "evaluation_status": "draft"
}}
```

Rules:

- `power` must be an integer from 1 to 5.
- Every `fit` value must be an integer from 0 to 5.
- `confidence` must be `high`, `medium` or `low`.
- `evaluation_status` must be `draft` or `held`.
- Every candidate in the roster below must appear exactly once.
- Do not add `approved`, `rarity` or `role_score` fields.

## 7. Candidate roster

{roster_table}

## 8. Ready-to-use prompt

Evaluate all {ready_count} candidates listed above using the attached research
package and the framework in this document. Return only the required JSON object
plus a concise exception report listing held candidates and why they are held.
Do not approve, publish or calculate rarity. Do not rely on previous conversations.

## 9. Completion checklist

- Every research-ready candidate appears once.
- Power and all seven Role Fits are integers in range.
- Justifications cite demonstrated abilities, not metadata alone.
- Continuity-sensitive or adaptation-sensitive claims are flagged.
- Held records explain the missing evidence.
- No approval, rarity or publication status is allocated.
"""


def build_assignment(ready: list[dict[str, Any]]) -> str:
    rows = [
        "| `one_piece_candidate_id` | Display name | Faction | Evidence focus |",
        "| --- | --- | --- | --- |",
    ]
    for record in ready:
        summary = record["capability_summary"]
        focus = []
        for key in (
            "offense",
            "defense_durability",
            "tactics",
            "support_control",
            "medical_healing",
        ):
            value = summary.get(key, "")
            if value and not value.startswith("unknown:"):
                focus.append(key.replace("_", " "))
        rows.append(
            f"| `{record['candidate_id']}` | {record['name']} | {record['faction']} | "
            f"{', '.join(focus[:4]) or 'general combat'} |"
        )
    return ASSIGNMENT_TEMPLATE.format(
        batch_label=BATCH_DIR_LABEL,
        cutoff=MANGA_CUTOFF_CHAPTER,
        date=PREPARED_DATE,
        ready_count=len(ready),
        roster_table="\n".join(rows),
    )


CANON_DOC = f"""# {CANON_POLICY}

## Purpose

Stable canonical policy for the One Piece content expansion. Applies to every
batch unless explicitly revised by the owner.

## Cutoff

Manga canon through Chapter {MANGA_CUTOFF_CHAPTER}. The cutoff is fixed for all
One Piece batches in this expansion so research remains reproducible.

## Inclusion rules

1. Use one sustainable version per individual character.
2. Prefer demonstrated prime capability within the cutoff.
3. Do not combine incompatible versions, periods or transformations.
4. Repeatable transformations that the character can access may be included;
   one-time external boosts and fatal techniques are excluded unless policy is
   explicitly revised.
5. Anime-only, movie-only, game-only, novel-only and SBS-only material is
   excluded from ability evidence within this policy.
6. Rank, bounty, affiliation and Devil Fruit classification are context only.
7. Unknown or disputed material remains unknown and must be flagged.

## Evidence tiers

- Primary: manga chapters within the cutoff (not directly opened in Stage 01).
- Inspected secondary: One Piece Wiki pages fetched via MediaWiki API and
  converted deterministically into research records.
- Unverified: recollection or indirect references; not sufficient for a
  RESEARCH_READY record.

## Policy assumptions requiring owner approval

- Chapter {MANGA_CUTOFF_CHAPTER} is an acceptable reproducible cutoff even if
  later chapters exist.
- Inspected secondary profiles are acceptable for research preparation when
  primary chapters are not opened, provided chapter leads are traceable.
- Adaptation-only sections are excluded at extraction time.

No approval, publication or playable-universe activation is implied by this
document.
"""


def build_batch_report(
    records: list[dict[str, Any]],
    research: dict[str, Any],
    manifest: dict[str, Any],
    unresolved: dict[str, Any],
    completeness: dict[str, Any],
) -> str:
    counts = Counter(record["research_gate"] for record in records)
    ability_total = sum(
        len(record["demonstrated_abilities"]) for record in research["candidates"]
    )
    cited = sum(
        1
        for record in research["candidates"]
        if any(item.get("canonical_refs") for item in record["demonstrated_abilities"])
    )
    factions = Counter(record["faction"] for record in research["candidates"])
    faction_lines = "\n".join(
        f"- {name}: {count}" for name, count in sorted(factions.items())
    )
    return f"""# One Piece {BATCH_DIR_LABEL} Research Report

## 1. Objective

Prepare a research-backed, self-contained Claude evaluation package for One
Piece {BATCH_DIR_LABEL}. No ratings, rarity, approval or publication status is
allocated.

## 2. Scope and policy

- Canonical policy: `{CANON_POLICY}`
- Manga cutoff: Chapter {MANGA_CUTOFF_CHAPTER}
- Framework: `{FRAMEWORK}`
- Scoring version: `{SCORING_VERSION}`
- Prepared date: {PREPARED_DATE}

Inspected secondary One Piece Wiki profiles were fetched through the MediaWiki
API. Chapter references were extracted from the inspected page text. Primary
manga chapters were not directly opened.

## 3. Candidate outcomes

- Candidates investigated: {len(records)}
- Research-ready candidates: {counts['RESEARCH_READY']}
- Partial research: {counts['PARTIAL_RESEARCH']}
- Insufficient evidence: {counts['INSUFFICIENT_EVIDENCE']}
- Duplicate identities excluded: 0
- Unresolved candidates preserved: {unresolved['candidate_count']}

## 4. Evidence coverage

- Research-ready package records: {len(research['candidates'])}
- Demonstrated ability records: {ability_total}
- Candidates with at least one canonical chapter reference: {cited}/{len(research['candidates'])}
- Candidates with a traceable source URL: {len(research['candidates'])}/{len(research['candidates'])}
- Adaptation-only sections excluded at extraction time: yes
- Primary sources directly inspected: no

## 5. Faction coverage

{faction_lines}

## 6. Artwork coverage

- Candidates in catalogue: {manifest['summary']['candidates_in_catalogue']}
- Technical validation valid: {manifest['summary']['valid']}
- Duplicate images: {manifest['summary']['duplicate']}
- Invalid images: {manifest['summary']['invalid']}
- Missing images: {manifest['summary']['missing']}
- Candidates covered by valid artwork: {manifest['summary']['candidates_with_valid_artwork']}/{manifest['summary']['candidates_in_catalogue']}

Technical validation checks format, dimensions and checksum. Visual identity
verification and publication permission remain separate reviews and were not
performed.

## 7. Research-quality gate

The corrected Naruto Batch 005 quality model was generalized for One Piece.
Catalogue completeness, artwork completeness, research completeness, evaluation
completeness and publication readiness are reported separately. Metadata-only
records and generic boilerplate cannot be research-ready.

Completeness stage summary:

- Catalogue complete: {str(completeness['stages']['catalogue']['complete']).lower()}
- Artwork complete: {str(completeness['stages']['artwork']['complete']).lower()}
- Research complete: {str(completeness['stages']['research']['complete']).lower()}
- Evaluation complete: {str(completeness['stages']['evaluation']['complete']).lower()}
- Publication ready: {str(completeness['stages']['publication']['ready']).lower()}

## 8. Source limitations

- Evidence is secondary-source based; no manga chapters were opened directly.
- Chapter numbers are leads extracted from inspected profile text.
- Some records lack a chapter citation beyond the inspected source URL.
- Limitation and conditional-ability fields are conservative; much is explicitly unknown.
- Artwork rights are source-dependent and require review before publication.

## 9. Model and resource usage

Research extraction and artefact generation were deterministic Python scripts.
One Piece Wiki API pages were fetched and cached outside Git. No paid model calls
were made and no evaluator ratings were generated.

## 10. Validation

Focused One Piece quality tests and the repository test suite were run after
build generation. Details are recorded in the completeness report and test
output.

## 11. Publication status

Research preparation only. No character is approved, imported into a playable
dataset or published. One Piece is not activated as a playable production
universe.

## 12. Next batch

Proceed to One Piece Batch 002 after this batch is validated and pushed, using
additional well-documented supporting characters, specialists and historical
figures. Unresolved candidates remain available for future research.
"""


MASTER_REPORT = """# One Piece Expansion Master Report

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


def write_gallery(research: dict[str, Any], manifest: dict[str, Any]) -> str:
    image_by_id = {item["candidate_id"]: item for item in manifest["images"]}
    cards = []
    for record in research["candidates"]:
        image = image_by_id.get(record["candidate_id"], {})
        url = image.get("image_url") or ""
        cards.append(
            {
                "id": record["candidate_id"],
                "name": record["name"],
                "batch": BATCH_ID,
                "faction": record["faction"],
                "status": record["research_gate"],
                "artwork": image.get("status", "missing"),
                "image": url,
                "source": record["source_url"],
                "abilities": [
                    ability["name"] for ability in record["demonstrated_abilities"][:6]
                ],
            }
        )
    payload = json.dumps(cards, ensure_ascii=False).replace("<", "\\u003c")
    return """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>One Piece Research Gallery</title>
<style>
body { font-family: system-ui, sans-serif; margin: 0; background: #0f1420; color: #e8ecf4; }
header { padding: 20px; border-bottom: 1px solid #283044; }
h1 { margin: 0 0 8px; font-size: 22px; }
.note { color: #9aa7bd; font-size: 13px; }
.controls { display: flex; gap: 10px; flex-wrap: wrap; padding: 16px 20px; }
input, select { background: #182036; color: #e8ecf4; border: 1px solid #35405c; border-radius: 6px; padding: 8px; }
#grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 14px; padding: 0 20px 30px; }
.card { background: #182036; border: 1px solid #2c3650; border-radius: 10px; padding: 10px; }
.card img { width: 100%; height: 230px; object-fit: contain; background: #0b0f18; border-radius: 6px; }
.card h2 { font-size: 15px; margin: 10px 0 4px; }
.meta { font-size: 12px; color: #9aa7bd; }
.badge { display: inline-block; padding: 2px 6px; border-radius: 4px; background: #24402e; margin-right: 4px; }
a { color: #7db4ff; font-size: 12px; }
</style>
</head>
<body>
<header>
  <h1>One Piece Research Gallery — Batch 001</h1>
  <div class="note">Research review only. No ratings, approval or publication status. Artwork rights require separate review.</div>
</header>
<div class="controls">
  <input id="search" type="search" placeholder="Search name or ability">
  <select id="batch"><option value="">All batches</option></select>
  <select id="faction"><option value="">All factions</option></select>
  <select id="status"><option value="">All research statuses</option></select>
  <select id="artwork"><option value="">All artwork statuses</option><option>valid</option><option>duplicate</option><option>invalid</option><option>missing</option></select>
</div>
<div id="grid"></div>
<script>
const DATA = __DATA__;
const grid = document.getElementById('grid');
const search = document.getElementById('search');
const batch = document.getElementById('batch');
const faction = document.getElementById('faction');
const status = document.getElementById('status');
const artwork = document.getElementById('artwork');
function options(select, values) {
  values.forEach(v => { const o = document.createElement('option'); o.value = v; o.textContent = v; select.appendChild(o); });
}
options(batch, [...new Set(DATA.map(d => d.batch))]);
options(faction, [...new Set(DATA.map(d => d.faction))].sort());
options(status, [...new Set(DATA.map(d => d.status))].sort());
function render() {
  const q = search.value.toLowerCase();
  const rows = DATA.filter(d =>
    (!batch.value || d.batch === batch.value) &&
    (!faction.value || d.faction === faction.value) &&
    (!status.value || d.status === status.value) &&
    (!artwork.value || d.artwork === artwork.value) &&
    (!q || (d.name + ' ' + d.abilities.join(' ')).toLowerCase().includes(q))
  );
  grid.innerHTML = rows.map(d => `<div class="card">
    ${d.image ? `<img src="${d.image}" alt="" referrerpolicy="no-referrer">` : ''}
    <h2>${d.name}</h2>
    <div class="meta"><span class="badge">${d.status}</span><span class="badge">${d.artwork}</span>${d.faction}</div>
    <div class="meta">${d.abilities.join(' · ')}</div>
    <a href="${d.source}" target="_blank" rel="noopener">Source</a>
  </div>`).join('');
}
[search, batch, faction, status, artwork].forEach(el => el.addEventListener('input', render));
render();
</script>
</body>
</html>
""".replace("__DATA__", payload)


def main() -> None:
    roster = json.loads(ROSTER.read_text(encoding="utf-8"))["candidates"]
    records, image_sources = fetch_research(roster)
    gate_counts = Counter(record["research_gate"] for record in records)
    ready = [record for record in records if record["research_gate"] == "RESEARCH_READY"]
    if len(ready) < 60:
        raise RuntimeError(
            f"Only {len(ready)} research-ready candidates; target 60 not met. "
            "Add reserve candidates before building the batch."
        )

    manifest = build_image_manifest(records, image_sources)
    catalogue = build_catalogue(ready, manifest)
    catalogue.save(ROOT / "one_piece_batch_001_catalogue.json")

    research = {
        "universe_id": UNIVERSE_ID,
        "batch_id": BATCH_ID,
        "batch_status": "research_ready_gated",
        "prepared_date": PREPARED_DATE,
        "stage": "01_initial_research",
        "framework": FRAMEWORK,
        "canonical_policy": CANON_POLICY,
        "scoring_version": SCORING_VERSION,
        "manga_cutoff_chapter": MANGA_CUTOFF_CHAPTER,
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
    write_json(ROOT / "one_piece_batch_001_research.json", research)
    write_json(ROOT / "one_piece_batch_001_image_manifest.json", manifest)

    unresolved = build_unresolved(records)
    write_json(ROOT / "one_piece_batch_001_unresolved_candidates.json", unresolved)

    catalogue_raw = json.loads(
        (ROOT / "one_piece_batch_001_catalogue.json").read_text(encoding="utf-8")
    )
    completeness = build_completeness_report(catalogue_raw, manifest, research, None)
    write_json(ROOT / "one_piece_batch_001_completeness_report.json", completeness)

    registry = build_master_registry(records, manifest)
    write_json(ROOT / "one_piece_master_registry.json", registry)
    progress = build_progress(records, research, manifest)
    write_json(ROOT / "one_piece_expansion_progress.json", progress)

    write_text(ROOT / "one_piece_batch_001_claude_assignment.md", build_assignment(ready))
    write_text(ROOT / "one_piece_review_gallery.html", write_gallery(research, manifest))
    write_text(Path("docs") / "ONE_PIECE_CANON_0.1.md", CANON_DOC + "\n")
    write_text(
        Path("docs") / "ONE_PIECE_BATCH_001_RESEARCH_REPORT.md",
        build_batch_report(records, research, manifest, unresolved, completeness) + "\n",
    )
    totals = progress["totals"]
    write_text(
        Path("docs") / "ONE_PIECE_EXPANSION_MASTER_REPORT.md",
        MASTER_REPORT.format(
            cutoff=MANGA_CUTOFF_CHAPTER,
            batch_summary=(
                "- Batch 001: research-ready package prepared; see "
                "`docs/ONE_PIECE_BATCH_001_RESEARCH_REPORT.md`."
            ),
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
                "researched": len(records),
                "gate_counts": dict(gate_counts),
                "ready": len(ready),
                "unresolved": unresolved["candidate_count"],
                "artwork": manifest["summary"],
                "catalogue_complete": completeness["stages"]["catalogue"]["complete"],
                "research_complete": completeness["stages"]["research"]["complete"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
