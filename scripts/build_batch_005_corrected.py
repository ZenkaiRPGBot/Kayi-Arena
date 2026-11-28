"""Build the corrected, research-gated Naruto Batch 005 package.

The earlier Stage 01 catalogue is reused for identities and validated artwork.
This script replaces metadata-only research records with capability research
produced in Stage 01B, selects only research-ready candidates, and preserves
everything else in a separate unresolved-candidate file.
"""

from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path
from typing import Any

from app.content.models import CandidateCatalogue
from scripts.batch_005_quality import is_substantive_ability, is_substantive_text, research_ready_valid
from scripts.consolidate_expansion import candidate_to_model

ROOT = Path("data")
TMP = Path(r"C:\Users\2024\AppData\Local\Temp\opencode")
SOURCE_CATALOGUE = ROOT / "naruto_candidates.json"
ORIGINAL_CATALOGUE = ROOT / "naruto_batch_005_original_catalogue.json"
RESEARCH_INPUTS = [
    TMP / "research_current_01.json",
    TMP / "research_current_02.json",
    TMP / "research_current_03.json",
    TMP / "research_current_04.json",
    TMP / "research_replacement_01.json",
    TMP / "research_replacement_02.json",
]
OUT_CATALOGUE = ROOT / "naruto_batch_005_catalogue.json"
OUT_RESEARCH = ROOT / "naruto_batch_005_research.json"
OUT_UNRESOLVED = ROOT / "naruto_batch_005_unresolved_candidates.json"
OUT_SELECTION = ROOT / "naruto_batch_005_selection_summary.json"
OUT_NAMES = ROOT / "naruto_batch_005_research_ready_names.json"
ARTWORK_EXCLUSIONS_PATH = ROOT / "naruto_batch_005_artwork_exclusions.json"

IMAGE_URL_OVERRIDES = {
    "dattebayo:901": ["https://static.wikia.nocookie.net/naruto/images/b/b2/Nishi_Infobox.png"]
}

# Continuity decisions recorded explicitly rather than silently merged.
CONTINUITY_EXCLUSIONS = {
    "dattebayo:1309": (
        "Shin Uchiha is a Boruto-era arc antagonist whose clone group creates an "
        "identity/ECV ambiguity. Preserved as unresolved, not silently merged or rated."
    ),
}

CAPABILITY_KEYS = [
    "combat_effectiveness",
    "offense",
    "defense_durability",
    "speed_mobility",
    "leadership",
    "tactics",
    "stealth_infiltration_assassination",
    "support_control",
    "medical_healing",
    "significant_achievements",
    "limitations",
    "conditional_abilities",
]


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def raw_text_for(name: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "_", name).strip("_")
    path = TMP / "batch005_raw" / f"{slug}.txt"
    return path.read_text(encoding="utf-8") if path.exists() else ""


def normalize_ref_text(text: str) -> str:
    """Normalise formatting differences without inventing a match.

    Fandom wikitext wraps citations in doubled apostrophes and often writes
    "pages 14-15" where a research note says "page 14, 15". Those are
    formatting differences. A bare chapter number appearing elsewhere in the
    article is not enough: the citation itself must be present.
    """
    text = text.lower().replace("\u2019", "'")
    text = re.sub(r"'{2,}", "", text)
    text = re.sub(r"[^\w\s\-]", " ", text)
    text = text.replace("\u2013", "-").replace("\u2014", "-")
    text = text.replace("pages", "page").replace("panels", "panel")
    return re.sub(r"\s+", " ", text).strip()


def canonical_ref_supported(ref: str, raw: str) -> bool:
    if not raw:
        return False
    return normalize_ref_text(ref) in normalize_ref_text(raw)


def clean_refs(refs: Any, raw: str) -> tuple[list[str], list[str]]:
    kept: list[str] = []
    dropped: list[str] = []
    for ref in refs or []:
        text = str(ref).strip()
        if not text:
            continue
        if canonical_ref_supported(text, raw):
            kept.append(text)
        else:
            dropped.append(text)
    return kept, dropped


def canon_admissible(record: dict[str, Any], raw: str) -> tuple[bool, str]:
    """Apply the NARUTO-CANON-0.1 default against adaptation-only evidence.

    Only references that survive the source-text check may support a
    capability. A databook mention in an unverified research note cannot be
    used to keep an adaptation-only record in the package.
    """
    version_text = " ".join(
        str(record.get(key) or "")
        for key in ("canonical_version", "canonical_version_basis", "gate_reason")
    ).lower()
    adaptation_only_version = (
        "anime-only" in version_text
        or "anime only" in version_text
        or "game-only" in version_text
        or "movie-only" in version_text
    )

    refs: list[str] = []
    for ability in record.get("demonstrated_abilities") or []:
        kept, _ = clean_refs(ability.get("canonical_refs") or [], raw)
        refs.extend(kept)
    for evidence in record.get("supporting_evidence") or []:
        kept, _ = clean_refs(evidence.get("canonical_refs") or [], raw)
        refs.extend(kept)

    has_manga_or_databook = any(
        "chapter" in ref.lower() or "databook" in ref.lower() for ref in refs
    )
    if has_manga_or_databook:
        return True, "none"

    adaptation_only_refs = any(
        any(marker in ref.lower() for marker in ("episode", "anime", "game", "movie", "film"))
        for ref in refs
    )
    if adaptation_only_version or adaptation_only_refs:
        return False, (
            "NARUTO-CANON-0.1 excludes adaptation-only additions by default; no verified "
            "manga chapter or databook reference supports the demonstrated ability."
        )
    return True, "none"


def score_record(record: dict[str, Any]) -> int:
    abilities = [item for item in record.get("demonstrated_abilities", []) if is_substantive_ability(item)]
    refs = sum(len(item.get("canonical_refs") or []) for item in abilities)
    fields = sum(1 for value in (record.get("capability_summary") or {}).values() if is_substantive_text(value))
    evidence = [
        item for item in record.get("supporting_evidence", [])
        if isinstance(item, dict) and str(item.get("url") or "").startswith("http")
    ]
    return len(abilities) * 4 + refs * 2 + fields + len(evidence) * 2


def main() -> None:
    source = load_json(SOURCE_CATALOGUE)
    original_catalogue = load_json(ORIGINAL_CATALOGUE)
    source_by_id = {item["candidate_id"]: item for item in source["candidates"]}
    original_by_id = {item["candidate_id"]: item for item in original_catalogue["candidates"]}
    current_order = [item["candidate_id"] for item in original_catalogue["candidates"]]

    researched: dict[str, dict[str, Any]] = {}
    replacement_order: list[str] = []
    group_counts: dict[str, dict[str, int]] = {}
    for path in RESEARCH_INPUTS:
        payload = load_json(path)
        counts: dict[str, int] = {}
        for record in payload["records"]:
            candidate_id = record["candidate_id"]
            if candidate_id in researched:
                raise ValueError(f"duplicate research record: {candidate_id}")
            researched[candidate_id] = record
            status = record["status"]
            counts[status] = counts.get(status, 0) + 1
            if path.name.startswith("research_replacement") and candidate_id not in replacement_order:
                replacement_order.append(candidate_id)
        group_counts[payload["group"]] = counts

    canon_exclusions: dict[str, str] = {}
    artwork_exclusions: dict[str, str] = {}
    if ARTWORK_EXCLUSIONS_PATH.exists():
        artwork_exclusions = {
            str(key): str(value)
            for key, value in load_json(ARTWORK_EXCLUSIONS_PATH).items()
        }
    all_candidate_ids = current_order + replacement_order
    for candidate_id in all_candidate_ids:
        record = researched.get(candidate_id)
        if not record or record.get("status") != "RESEARCH_READY":
            continue
        admissible, reason = canon_admissible(record, raw_text_for(record["name"]))
        if not admissible:
            canon_exclusions[candidate_id] = reason

    ready_current = [
        candidate_id for candidate_id in current_order
        if researched.get(candidate_id, {}).get("status") == "RESEARCH_READY"
        and candidate_id not in CONTINUITY_EXCLUSIONS
        and candidate_id not in canon_exclusions
        and candidate_id not in artwork_exclusions
    ]
    ready_replacement = sorted(
        [
            candidate_id for candidate_id in replacement_order
            if researched.get(candidate_id, {}).get("status") == "RESEARCH_READY"
            and candidate_id not in canon_exclusions
            and candidate_id not in artwork_exclusions
        ],
        key=lambda candidate_id: score_record(researched[candidate_id]),
        reverse=True,
    )
    selected_ids = (ready_current + ready_replacement)[:100]
    selected_set = set(selected_ids)

    # Build catalogue records from the original validated records where possible.
    catalogue_records: list[dict[str, Any]] = []
    for candidate_id in selected_ids:
        base = original_by_id.get(candidate_id) or source_by_id[candidate_id]
        record = json.loads(json.dumps(base))
        record["review_status"] = "pending"
        record["canonical_eligibility"] = record.get("canonical_eligibility", "eligible")
        if candidate_id in IMAGE_URL_OVERRIDES:
            urls = list(IMAGE_URL_OVERRIDES[candidate_id])
            record["image_urls"] = urls
            record["images"] = [
                {
                    "url": url,
                    "source": record.get("source", "dattebayo"),
                    "status": "pending",
                    "rights": "source-dependent; review before publication",
                }
                for url in urls
            ]
        catalogue_records.append(record)

    catalogue = CandidateCatalogue(
        universe="Naruto",
        source="dattebayo",
        provider="dattebayo",
        generated_at=date.today().isoformat(),
        stats={
            "targets": len(selected_ids),
            "matched": len(catalogue_records),
            "unmatched": 0,
        },
        candidates=[candidate_to_model(record) for record in catalogue_records],
    )
    catalogue.save(OUT_CATALOGUE)

    research_candidates: list[dict[str, Any]] = []
    for candidate_id in selected_ids:
        record = researched[candidate_id]
        base = source_by_id.get(candidate_id) or original_by_id[candidate_id]
        raw = raw_text_for(record["name"])
        dropped_refs: list[str] = []
        abilities: list[dict[str, Any]] = []
        for ability in record.get("demonstrated_abilities") or []:
            cleaned = json.loads(json.dumps(ability))
            kept, dropped = clean_refs(cleaned.get("canonical_refs") or [], raw)
            cleaned["canonical_refs"] = kept
            dropped_refs.extend(dropped)
            if is_substantive_ability(cleaned):
                abilities.append(cleaned)
        evidence: list[dict[str, Any]] = []
        for item in record.get("supporting_evidence") or []:
            cleaned = json.loads(json.dumps(item))
            kept, dropped = clean_refs(cleaned.get("canonical_refs") or [], raw)
            cleaned["canonical_refs"] = kept
            dropped_refs.extend(dropped)
            if str(cleaned.get("url") or "").startswith("http"):
                evidence.append(cleaned)
        capability_summary = {
            key: str((record.get("capability_summary") or {}).get(key) or "unknown: no demonstrated evidence in the supplied source")
            for key in CAPABILITY_KEYS
        }
        candidate = {
            "candidate_id": candidate_id,
            "name": record["name"],
            "aliases": base.get("aliases") or [],
            "species": base.get("species"),
            "source": base.get("source", "dattebayo"),
            "source_url": base.get("source_url") or record.get("supporting_evidence", [{}])[0].get("url", ""),
            "rank": (base.get("source_metadata") or {}).get("rank"),
            "affiliation": (base.get("source_metadata") or {}).get("affiliation") or [],
            "clan": (base.get("source_metadata") or {}).get("clan"),
            "titles": (base.get("source_metadata") or {}).get("titles") or [],
            "debut": base.get("debut") or {},
            "classification": base.get("classification") or [],
            "canonical_eligibility": base.get("canonical_eligibility", "eligible"),
            "eligibility_reason": base.get("eligibility_reason", ""),
            "image_status": "pending",
            "status": "RESEARCH_READY",
            "research_gate": "RESEARCH_READY",
            "research_status": "RESEARCH_READY",
            "canonical_version": record.get("canonical_version") or "not established",
            "canonical_version_basis": record.get("canonical_version_basis") or "not established",
            "capability_summary": capability_summary,
            "demonstrated_abilities": abilities,
            "supporting_evidence": evidence,
            "gate_reason": record.get("gate_reason") or "substantive demonstrated capability with traceable source",
            "continuity_note": CONTINUITY_EXCLUSIONS.get(candidate_id, "none"),
            "evidence_check": {
                "verification_level": "inspected_secondary",
                "canonical_refs_verified_against_inspected_page_text": True,
                "unsupported_refs_dropped": sorted(set(dropped_refs)),
                "primary_sources_directly_inspected": False,
            },
            "notes": [
                "Stage 01B corrective research. No numerical ratings or rarity are allocated.",
                "Catalogue metadata is context only; ratings must rest on demonstrated abilities above.",
            ],
        }
        valid, errors = research_ready_valid(candidate)
        if not valid:
            raise ValueError(f"research-ready gate failed for {candidate_id}: {errors}")
        research_candidates.append(candidate)

    status_counts: dict[str, int] = {}
    for record in researched.values():
        status_counts[record["status"]] = status_counts.get(record["status"], 0) + 1

    research = {
        "universe_id": "naruto",
        "batch_id": "naruto-batch-005",
        "batch_status": "research_ready_gated",
        "prepared_date": date.today().isoformat(),
        "stage": "01B_corrective_research",
        "framework": "EVAL-FRAMEWORK-1.0",
        "canonical_policy": "NARUTO-CANON-0.1",
        "scoring_version": "SCORE-1.0",
        "candidate_count": len(research_candidates),
        "research_gate_counts": status_counts,
        "research_ready_count": len(research_candidates),
        "unresolved_count": len(researched) - len(selected_ids),
        "notes": [
            "This package contains only RESEARCH_READY candidates with demonstrated capabilities and traceable secondary sources.",
            "No Power, Role Fit, rarity, score, approval or publication status is allocated.",
            "Sources are inspected secondary profiles; chapter/databook references were checked against the inspected page text but primary sources were not opened.",
            "The original placeholder evaluation is preserved separately and is not imported.",
            "Continuity-sensitive entries that were not research-ready are preserved in the unresolved file.",
        ],
        "manual_identity_mapping_candidates": [
            {
                "name": "Enma",
                "status": "manual_identity_mapping_required",
                "reason": "Appears in prior Batch 004-B files with no exact Dattebayo catalogue record; not a permanent exclusion.",
                "action_for_integration": "Resolve identity manually before any future evaluation.",
            }
        ],
        "candidates": research_candidates,
    }
    OUT_RESEARCH.write_text(json.dumps(research, indent=2, ensure_ascii=False), encoding="utf-8")

    unresolved_candidates: list[dict[str, Any]] = []
    for candidate_id, record in researched.items():
        if candidate_id in selected_set:
            continue
        reason = record.get("gate_reason") or "not selected for the research-ready package"
        if candidate_id in CONTINUITY_EXCLUSIONS:
            reason = CONTINUITY_EXCLUSIONS[candidate_id]
        elif candidate_id in canon_exclusions:
            reason = canon_exclusions[candidate_id]
        elif candidate_id in artwork_exclusions:
            reason = artwork_exclusions[candidate_id]
        entry = {
            "candidate_id": candidate_id,
            "name": record["name"],
            "research_gate": record["status"],
            "reason": reason,
            "source_url": record.get("supporting_evidence", [{}])[0].get("url")
            or source_by_id.get(candidate_id, {}).get("source_url", ""),
            "origin": "original_batch_005" if candidate_id in current_order else "replacement_pool",
            "continuity_note": CONTINUITY_EXCLUSIONS.get(candidate_id, "none"),
        }
        unresolved_candidates.append(entry)
    unresolved = {
        "batch_id": "naruto-batch-005",
        "prepared_date": date.today().isoformat(),
        "excluded_from_evaluation_package": True,
        "policy": "Preserved for traceability. No placeholder rating is imported and no identity is permanently excluded unless stated.",
        "continuity_exclusions": [
            {"candidate_id": key, "name": researched.get(key, {}).get("name", ""), "reason": value}
            for key, value in CONTINUITY_EXCLUSIONS.items()
        ],
        "canon_exclusions": [
            {"candidate_id": key, "name": researched.get(key, {}).get("name", ""), "reason": value}
            for key, value in canon_exclusions.items()
        ],
        "artwork_exclusions": [
            {"candidate_id": key, "name": researched.get(key, {}).get("name", ""), "reason": value}
            for key, value in artwork_exclusions.items()
        ],
        "manual_identity_mapping_candidates": research["manual_identity_mapping_candidates"],
        "candidates": unresolved_candidates,
    }
    OUT_UNRESOLVED.write_text(json.dumps(unresolved, indent=2, ensure_ascii=False), encoding="utf-8")

    selection_summary = {
        "batch_id": "naruto-batch-005",
        "prepared_date": date.today().isoformat(),
        "original_candidates_researched": len(current_order),
        "replacement_candidates_researched": len(replacement_order),
        "group_counts": group_counts,
        "status_counts_all_researched": status_counts,
        "original_research_ready": len(ready_current),
        "continuity_excluded_original": sorted(CONTINUITY_EXCLUSIONS),
        "adaptation_only_exclusions": sorted(canon_exclusions),
        "artwork_exclusions": sorted(artwork_exclusions),
        "replacement_research_ready": len(ready_replacement),
        "replacements_selected": [candidate_id for candidate_id in selected_ids if candidate_id not in current_order],
        "original_candidates_removed": [
            candidate_id for candidate_id in current_order if candidate_id not in selected_ids
        ],
        "final_research_ready_count": len(selected_ids),
        "target_100_reached": len(selected_ids) == 100,
        "padding_used": False,
    }
    OUT_SELECTION.write_text(json.dumps(selection_summary, indent=2, ensure_ascii=False), encoding="utf-8")
    OUT_NAMES.write_text(
        json.dumps([researched[candidate_id]["name"] for candidate_id in selected_ids], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"final_research_ready={len(selected_ids)} unresolved={len(unresolved_candidates)}")
    print(f"wrote {OUT_CATALOGUE}")
    print(f"wrote {OUT_RESEARCH}")
    print(f"wrote {OUT_UNRESOLVED}")
    print(f"wrote {OUT_SELECTION}")
    print(f"wrote {OUT_NAMES}")


if __name__ == "__main__":
    main()
