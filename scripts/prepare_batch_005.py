"""Prepare Naruto Batch 005 research and catalogue deliverables.

Stage 01 only: candidate selection, factual research, artwork collection.
No Power, Role Fit or rarity is allocated here.
"""

from __future__ import annotations

import json
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

from app.content.models import CandidateCatalogue
from scripts.batch_005_quality import assess_catalogue, assess_research
from scripts.consolidate_expansion import candidate_to_model

ROOT = Path("data")
TOP100 = ROOT / "naruto_batch_005_selected_names.json"
SOURCE_CATALOGUE = ROOT / "naruto_candidates.json"

OUT_CAT = ROOT / "naruto_batch_005_catalogue.json"
OUT_RESEARCH = ROOT / "naruto_batch_005_research.json"

# Artwork corrections found during Stage 01 source review. The catalogue's
# Nishi image URL returns HTTP 404; the page currently exposes Nishi_Infobox.png.
IMAGE_URL_OVERRIDES = {
    "dattebayo:901": [
        "https://static.wikia.nocookie.net/naruto/images/b/b2/Nishi_Infobox.png"
    ],
}

# Secondary Fandom pages directly inspected during Stage 01 evidence review.
DIRECTLY_INSPECTED_PAGES = {
    "dattebayo:695": (
        "Kosuke (Kiri-nin): page cites Fourth Databook p.207 and Naruto chapters 604-605 "
        "(anime Shippūden episode 345); Anbu, sword implied, killed during Obito's rampage."
    ),
    "dattebayo:901": (
        "Nishi (sensor): page cites Boruto chapter 39 and anime episode 205 credits; "
        "Konoha sensor/Jōnin tasked with monitoring Kawaki and Boruto."
    ),
}

ALIASES = {
    "C (Kumogakure shinobi)": "C",
    "Reto — First Kazekage": "Reto",
    "Shamon — Second Kazekage": "Shamon",
    "Byakuren — First Mizukage": "Byakuren",
    "Ishikawa — First Tsuchikage": "Ishikawa",
    "A — First Raikage": "A (First Raikage)",
    "A — Second Raikage": "A (Second Raikage)",
    "Kiri — Allied Shinobi Forces": "Kiri (ninja)",
    "Hoheto Hyuga": "Hoheto Hyūga",
    "Yoroi Akado": "Yoroi Akadō",
    "Chukichi": "Chūkichi",
    "Kakko": "Kakkō",
    "Choji Akimichi": "Chōji Akimichi",
    "Chojuro": "Chōjūrō",
    "Nono Yakushi": "Nonō Yakushi",
}


def norm(value: str) -> str:
    return unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode().lower().strip()


def as_list(value) -> list:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def fmt(value) -> str:
    if value is None or value == "" or value == []:
        return "not recorded"
    if isinstance(value, list):
        return ", ".join(str(item) for item in value)
    if isinstance(value, dict):
        return "; ".join(f"{key}: {val}" for key, val in value.items())
    return str(value)


def main() -> None:
    selected = json.loads(TOP100.read_text(encoding="utf-8"))
    source = json.loads(SOURCE_CATALOGUE.read_text(encoding="utf-8"))
    by_exact = {c["name"]: c for c in source["candidates"]}
    by_norm = {norm(c["name"]): c for c in source["candidates"]}
    for alias, target in ALIASES.items():
        if norm(target) in by_norm:
            by_norm[norm(alias)] = by_norm[norm(target)]

    missing = []
    matched_candidates = []
    for name in selected:
        # Prefer an exact page-name match. Normalised fallback can collapse
        # distinct identities such as Kosuke (Kiri-nin) and Kōsuke (toad).
        candidate = by_exact.get(name) or by_norm.get(norm(name))
        if candidate is None:
            missing.append(name)
            continue
        merged_source = json.loads(json.dumps(candidate))
        if candidate.get("candidate_id") in IMAGE_URL_OVERRIDES:
            corrected_urls = list(IMAGE_URL_OVERRIDES[candidate["candidate_id"]])
            merged_source["image_urls"] = corrected_urls
            merged_source["images"] = [
                {
                    "url": url,
                    "source": candidate.get("source", "dattebayo"),
                    "status": "pending",
                    "rights": "source-dependent; review before publication",
                }
                for url in corrected_urls
            ]
        matched_candidates.append((name, merged_source))

    # Build catalogue (KA-IMPORT-1.0 catalogue batch) from matched source records.
    catalogue_characters = []
    for name, candidate in matched_candidates:
        merged = json.loads(json.dumps(candidate))
        merged["review_status"] = "pending"
        merged["canonical_eligibility"] = merged.get("canonical_eligibility", "eligible")
        if candidate.get("candidate_id") in IMAGE_URL_OVERRIDES:
            merged["notes"] = list(merged.get("notes", [])) + [
                "Stage 01 artwork URL corrected from source catalogue after a 404 check."
            ]
        catalogue_characters.append(merged)

    catalogue = CandidateCatalogue(
        universe="Naruto",
        source="dattebayo",
        provider="dattebayo",
        generated_at=datetime.now(timezone.utc).isoformat(),
        stats={
            "targets": len(selected),
            "matched": len(catalogue_characters),
            "unmatched": len(missing),
        },
        candidates=[candidate_to_model(c) for c in catalogue_characters],
    )
    catalogue.save(OUT_CAT)

    # Build research package.
    research_candidates = []
    for name, candidate in matched_candidates:
        sm = candidate.get("source_metadata", {}) or {}
        personal = sm.get("personal", {}) or {}
        debut = candidate.get("debut", {}) or {}
        classification = as_list(candidate.get("classification") or sm.get("classification"))
        rank = sm.get("rank")
        affiliation = as_list(sm.get("affiliation"))
        clan = sm.get("clan")
        titles = as_list(sm.get("titles"))
        aliases = as_list(candidate.get("aliases"))

        personal_classification = personal.get("classification")
        kekkei = personal.get("kekkeiGenkai")
        occupation = personal.get("occupation")
        team = personal.get("team")
        partner = personal.get("partner")
        status = personal.get("status")

        classification_text = fmt(classification)
        affiliation_text = fmt(affiliation)
        titles_text = "; ".join(str(item) for item in titles) if titles else "none recorded"
        rank_text = fmt(rank)
        kekkei_text = fmt(kekkei)
        occupation_text = fmt(occupation)
        team_text = fmt(team)
        partner_text = fmt(partner)

        classification_haystack = " ".join(
            str(item) for item in classification + as_list(personal_classification)
        ).lower()
        is_medical = "medic" in classification_haystack or "medical" in classification_haystack
        is_sensor = "sensor" in classification_haystack

        research = {
            "identity": (
                f"{candidate['name']} (catalogue: {candidate.get('source_url', '')}). "
                f"Aliases: {', '.join(str(item) for item in aliases) if aliases else 'none recorded'}. "
                f"Recorded name forms: {titles_text}. "
                f"Species: {candidate.get('species') or 'not recorded'}."
            ),
            "aliases": aliases,
            "canonical_appearance_versions": (
                f"Debut manga: {debut.get('manga') or 'not recorded'}; "
                f"anime: {debut.get('anime') or 'not recorded'}; "
                f"other media: {fmt(debut.get('appearsIn'))}. "
                f"Recorded status: {fmt(status)}; rank: {rank_text}. "
                "Canonical version for evaluation should be fixed by Claude per NARUTO-CANON-0.1 "
                "using the documented arc of best feats. Do not combine incompatible periods."
            ),
            "offensive_capabilities": [
                "No individual jutsu or combat feats are transcribed here; Claude must derive offensive "
                "profile from rank, classification, clan/kekkei genkai and titles below plus independently verified sources.",
                f"Rank: {rank_text}.",
                f"Classification: {classification_text}.",
                f"Kekkei genkai recorded by source metadata: {kekkei_text}.",
                f"Titles/name forms: {titles_text}.",
            ],
            "defensive_capabilities_and_durability": [
                "Durability and defensive feats are not independently verified in this package. "
                "Claude should treat rank and affiliation as a coarse prior only and prefer primary evidence.",
                f"Affiliation: {affiliation_text}.",
                f"Recorded status: {fmt(status)}.",
            ],
            "speed_and_combat_effectiveness": [
                "No speed or reaction feats are recorded in the source metadata. "
                "Claude must not infer speed from rank alone; mark unknown where unsupported.",
                f"Classification: {classification_text}.",
                f"Team/partner: {team_text} / {partner_text}.",
            ],
            "leadership": [
                f"Rank: {rank_text}.",
                f"Occupation: {occupation_text}.",
                f"Team: {team_text}.",
                f"Titles: {titles_text}.",
                "Leadership evidence must be verified from primary material; rank, title or team membership "
                "implies but does not prove command experience.",
            ],
            "tactical_intelligence": [
                "Tactical feats are not recorded in the source metadata. Claude should rely on verified mission roles.",
                f"Occupation: {occupation_text}.",
                f"Team/partner: {team_text} / {partner_text}.",
            ],
            "stealth_and_infiltration": [
                "No stealth or infiltration feats are recorded in the source metadata.",
                f"Classification: {classification_text}.",
                f"Occupation: {occupation_text}.",
            ],
            "support_and_battlefield_control": [
                "No support or battlefield-control feats are recorded beyond classification, rank and affiliation.",
                f"Classification: {classification_text}.",
                f"Sensor classification present: {'yes' if is_sensor else 'no'}.",
                f"Medical classification present: {'yes' if is_medical else 'no'}.",
            ],
            "medical_and_healing": [
                ("Medical/medic classification present; medical capability must be verified from primary material before rating."
                 if is_medical else
                 "No medical classification recorded; healing capability should not be assumed."),
            ],
            "significant_achievements": [
                f"Debut: manga {debut.get('manga') or 'n/a'}, anime {debut.get('anime') or 'n/a'}.",
                f"Affiliation: {affiliation_text}.",
                f"Clan: {fmt(clan)}.",
                f"Occupation/team: {occupation_text} / {team_text}.",
            ],
            "limitations_and_weaknesses": [
                "Limitations are not documented in the source metadata. Claude should note 'unknown' where unsupported.",
                f"Recorded status: {fmt(status)}.",
            ],
            "conditional_abilities_and_transformations": [
                (f"Kekkei genkai recorded by source metadata: {kekkei_text}. Classify before use per EVAL-FRAMEWORK-1.0."
                 if kekkei else
                 "No conditional abilities or transformations are recorded in the source metadata."),
                f"Classification: {classification_text}.",
            ],
            "relevant_canonical_evidence": [
                f"Source: {candidate.get('source_url', '')}",
                (
                    "Verification level: inspected_secondary (Fandom character page directly inspected on 2026-11-27; "
                    "primary citations listed there were not directly inspected)."
                    if candidate.get("candidate_id") in DIRECTLY_INSPECTED_PAGES else
                    "Verification level: search_result_summary (Dattebayo-derived metadata; page not directly inspected this stage)."
                ),
            ],
        }

        evidence_level = (
            "inspected_secondary"
            if candidate.get("candidate_id") in DIRECTLY_INSPECTED_PAGES
            else "search_result_summary"
        )
        evidence_leads = [
            {
                "url": candidate.get("source_url"),
                "lead": f"Dattebayo-derived candidate record for {candidate['name']}.",
                "verification_level": evidence_level,
                "source_note": (
                    "Fandom page directly inspected on 2026-11-27; cited primary references were not opened."
                    if candidate.get("candidate_id") in DIRECTLY_INSPECTED_PAGES else
                    "Metadata (rank, affiliation, clan, titles, debut, classification) from the existing catalogue; page not directly inspected this stage."
                ),
            }
        ]
        if candidate.get("candidate_id") in DIRECTLY_INSPECTED_PAGES:
            evidence_leads.append(
                {
                    "url": candidate.get("source_url"),
                    "lead": DIRECTLY_INSPECTED_PAGES[candidate["candidate_id"]],
                    "verification_level": "inspected_secondary",
                    "source_note": "Directly inspected Fandom page; citations to databook/chapters are leads, not primary verification.",
                }
            )

        research_candidates.append(
            {
                "candidate_id": candidate["candidate_id"],
                "name": candidate["name"],
                "aliases": aliases,
                "species": candidate.get("species"),
                "source": candidate.get("source", "dattebayo"),
                "source_url": candidate.get("source_url", ""),
                "rank": rank,
                "affiliation": affiliation,
                "clan": clan,
                "titles": titles,
                "personal": personal,
                "debut": debut,
                "classification": classification,
                "canonical_eligibility": candidate.get("canonical_eligibility", "eligible"),
                "eligibility_reason": candidate.get("eligibility_reason", ""),
                "image_status": "pending",
                # This generator intentionally produces metadata-only research.
                # It must never be reported as research-complete.
                "research_gate": "INSUFFICIENT_EVIDENCE",
                "research": research,
                "evidence_level": evidence_level,
                "evidence_leads": evidence_leads,
                "notes": [
                    "Stage 01 research only. No Power, Role Fit or rarity allocated.",
                    "Detailed ability research is limited to source metadata; Claude should verify feats from primary material where ratings depend on them.",
                ],
            }
        )

    research = {
        "universe_id": "naruto",
        "batch_id": "naruto-batch-005",
        "batch_status": "research",
        "prepared_date": "2026-11-27",
        "stage": "01_research_and_catalogue_preparation",
        "framework": "EVAL-FRAMEWORK-1.0",
        "canonical_policy": "NARUTO-CANON-0.1",
        "scoring_version": "SCORE-1.0",
        "rarity_version": "RARITY-0.2",
        "candidate_count": len(research_candidates),
        "unmatched_selected": missing,
        "notes": [
            "No ratings are allocated in this package. Claude performs independent evaluation.",
            "Evidence levels are conservative: most records are search_result_summary; only the two directly inspected secondary pages are marked inspected_secondary.",
            "No primary manga, databook or anime material was directly inspected in Stage 01.",
            "Calibration tiers are marked separately in naruto_batch_005_calibration.json; no record is labelled approved.",
        ],
        "manual_identity_mapping_candidates": [
            {
                "name": "Enma",
                "status": "manual_identity_mapping_required",
                "reason": (
                    "Enma appears in prior Batch 004-B review/evaluation files but has no exact Dattebayo catalogue "
                    "record and was unmatched during expansion integration. This is not a permanent exclusion."
                ),
                "action_for_integration": (
                    "Resolve the intended identity/alias manually before adding any future evaluation; do not merge "
                    "into a Batch 005 rating without an explicit identity decision."
                ),
                "evidence_leads": [
                    {
                        "url": "data/naruto_batch_004_b_evaluations.json",
                        "lead": "Prior local evaluation record containing Enma.",
                        "verification_level": "local_dataset",
                    },
                    {
                        "url": "data/naruto_batch_004_b_review_notes.md",
                        "lead": "Prior local review notes discussing Enma.",
                        "verification_level": "local_dataset",
                    },
                ],
            }
        ],
        "candidates": research_candidates,
    }
    OUT_RESEARCH.write_text(json.dumps(research, indent=2, ensure_ascii=False), encoding="utf-8")

    catalogue_status = assess_catalogue(json.loads(OUT_CAT.read_text(encoding="utf-8")))
    research_status = assess_research(research)
    print(f"matched={len(matched_candidates)} unmatched={len(missing)}")
    if missing:
        print("MISSING:", missing)
    print(
        "catalogue_complete={catalogue} research_classification_valid={research} "
        "research_ready={ready} research_complete=False "
        "evaluation_complete=False publication_ready=False".format(
            catalogue=catalogue_status["complete"],
            research=research_status["classification_complete"],
            ready=research_status["status_counts"]["RESEARCH_READY"],
        )
    )
    print(
        "warning: this generator only maps catalogue metadata; it does not produce "
        "substantive research or a Claude-ready package."
    )
    print(f"wrote {OUT_CAT}")
    print(f"wrote {OUT_RESEARCH}")


if __name__ == "__main__":
    main()
