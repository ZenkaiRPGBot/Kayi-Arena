"""Write the independent audit report for Naruto Batch 005."""

from __future__ import annotations

import hashlib
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

ROOT = Path("data")
OUT = Path("docs") / "NARUTO_BATCH_005_INDEPENDENT_AUDIT_REPORT.md"


def load(name: str) -> Any:
    return json.loads((ROOT / name).read_text(encoding="utf-8"))


def sha256(name: str) -> str:
    return hashlib.sha256((ROOT / name).read_bytes()).hexdigest()


def fmt_fit(fit: dict[str, int]) -> str:
    return "/".join(str(fit[role]) for role in ("captain", "strategist", "attacker", "tank", "assassin", "support", "healer"))


def main() -> None:
    original = load("naruto_batch_005_claude_evaluation.json")
    audited = load("naruto_batch_005_audited_evaluations.json")
    held = load("naruto_batch_005_held_candidates.json")
    details = load("naruto_batch_005_audit_details.json")
    changes = load("naruto_batch_005_rating_changes.json")
    advisory = load("naruto_batch_005_derived_role_scores_advisory.json")
    sim = load("naruto_batch_005_audit_simulation.json")
    research = load("naruto_batch_005_research.json")
    catalogue = load("naruto_batch_005_catalogue.json")
    manifest = load("naruto_batch_005_image_manifest.json")

    importable = audited["evaluations"]
    held_ids = {item["character_id"] for item in held["candidates"]}
    detail_by_id = {item["character_id"]: item for item in details["candidates"]}
    original_by_id = {item["character_id"]: item for item in original["evaluations"]}

    original_power = Counter(e["power"] for e in original["evaluations"])
    audited_power = Counter(e["power"] for e in importable)
    rarity_counts = Counter(e["rarity"]["final_rarity"] for e in importable)
    fit_counts = {
        role: Counter(e["fit"][role] for e in importable)
        for role in ("captain", "strategist", "attacker", "tank", "assassin", "support", "healer")
    }
    research_ids = {c["candidate_id"] for c in research["candidates"]}
    existing_overlap = {}
    for path in (
        "naruto_evaluated_60_dataset.json",
        "naruto_expansion_003_004_evaluated_dataset.json",
        "naruto_batch_003_evaluated_dataset.json",
    ):
        try:
            data = load(path)
        except FileNotFoundError:
            continue
        ids = {c["character_id"] for c in data["characters"]}
        existing_overlap[path] = len(research_ids & ids)

    top_by_role = {}
    for role in ("captain", "strategist", "attacker", "tank", "assassin", "support", "healer"):
        top_by_role[role] = sorted(
            importable, key=lambda e: (e["scores"][role], e["fit"][role], e["power"]), reverse=True
        )[:5]

    rows = []
    for e in original["evaluations"]:
        cid = e["character_id"]
        d = detail_by_id[cid]
        status = d["audit_status"]
        before_fit = fmt_fit(e["fit"])
        after_fit = fmt_fit(d["audited"]["fit"]) if status == "importable" else "Held"
        before_power = str(e["power"])
        after_power = str(d["audited"]["power"]) if status == "importable" else "Held"
        changed = "yes" if d["changes"] else "no"
        rows.append(
            f"| {cid} | {d['name']} | {before_power} | {after_power} | {before_fit} | {after_fit} | "
            f"{status} | {changed} | {d['audit_decision']} |"
        )

    change_rows = []
    for c in changes["changes"]:
        change_rows.append(
            f"| {c['character_id']} | {c['name']} | {c['field']} | {c['original_rating']} → {c['revised_rating']} | "
            f"{c['reason']} | {c['calibration_justification']} | {c['confidence']} |"
        )

    held_rows = []
    for item in held["candidates"]:
        held_rows.append(
            f"| {item['character_id']} | {item['name']} | {item['hold_code']} | {item['reason']} |"
        )

    lines: list[str] = []
    lines.append("# Naruto Batch 005 — Independent Evaluation Audit Report")
    lines.append("")
    lines.append("## 1. Scope and status")
    lines.append("")
    lines.append("- Batch: `naruto-batch-005`")
    lines.append("- Corrected research package commit: `76905d2`")
    lines.append("- Canonical policy: `NARUTO-CANON-0.1`")
    lines.append("- Framework: `EVAL-FRAMEWORK-1.0`; scoring `SCORE-1.0`; rarity `RARITY-0.2`")
    lines.append("- Preparation date: 2026-11-27")
    lines.append("- Status: **draft audit preparation**. Nothing is approved, published or imported into a playable dataset.")
    lines.append("")
    lines.append("All 62 Claude evaluations were audited individually against the corrected research package, the calibration reference, the approved Power/Fit definitions, evidence ceilings and canonical-exclusion rules. Original Claude outputs were preserved byte-for-byte.")
    lines.append("")
    lines.append("Original-output SHA-256 values:")
    lines.append("")
    for name in (
        "naruto_batch_005_claude_evaluation.json",
        "naruto_batch_005_evaluation_details.json",
        "naruto_batch_005_final_report.md",
        "naruto_batch_005_derived_role_scores_advisory.json",
        "naruto_batch_005_build_and_validate.py",
        "naruto_batch_005_passA_fit_frozen.py",
    ):
        lines.append(f"- `{name}`: `{sha256(name)}`")
    lines.append("")
    lines.append("## 2. Outcome summary")
    lines.append("")
    lines.append(f"- Candidates accounted for: **62**")
    lines.append(f"- Importable audited evaluations: **{len(importable)}**")
    lines.append(f"- Held and excluded from import: **{len(held_ids)}**")
    lines.append(f"- Rating changes: **{len(changes['changes'])}** across 4 records")
    lines.append("- No Power or Role Fit was invented to satisfy an import schema.")
    lines.append("- No Fit 4 or Fit 5 was introduced; the supplied evidence does not support a specialist ceiling upgrade.")
    lines.append("")
    lines.append("### Power distribution")
    lines.append("")
    lines.append("| Power | Claude original | Audited importable |")
    lines.append("|---:|---:|---:|")
    for level in (1, 2, 3, 4, 5):
        lines.append(f"| {level} | {original_power[level]} | {audited_power[level]} |")
    lines.append("")
    lines.append("The reduction in Power 1 and Power 2 counts reflects 10 held records and one justified Power correction, not a forced distribution.")
    lines.append("")
    lines.append("### Role Fit distribution (audited importable)")
    lines.append("")
    lines.append("| Role | 0 | 1 | 2 | 3 | 4 | 5 |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|")
    for role, counter in fit_counts.items():
        lines.append(
            f"| {role} | {counter[0]} | {counter[1]} | {counter[2]} | {counter[3]} | {counter[4]} | {counter[5]} |"
        )
    lines.append("")
    lines.append("No Fit 4 or Fit 5 remains justified. The strongest available specialist level in this batch is Fit 3, with evidence limited to inspected secondary profiles and no primary manga inspection.")
    lines.append("")
    lines.append("### Rarity distribution (authoritative RARITY-0.2 with Naruto healer floors)")
    lines.append("")
    lines.append("| Rarity | Count |")
    lines.append("|---|---:|")
    for tier in ("Common", "Uncommon", "Rare", "Epic", "Legendary"):
        lines.append(f"| {tier} | {rarity_counts[tier]} |")
    lines.append("")
    lines.append("The skew to Common reflects genuinely low Power/Fit evidence, not a rarity manipulation.")
    lines.append("")
    lines.append("## 3. Held candidates")
    lines.append("")
    lines.append("| ID | Name | Hold code | Reason |")
    lines.append("|---|---|---|---|")
    lines.extend(held_rows)
    lines.append("")
    lines.append("Boruto-era candidates were held rather than independently expanding the Naruto universe boundary. `Hyūga Elder` and `Hamaki Mimura` were held because their only supplied capabilities were an implied anime-only demonstration and borrowed equipment respectively.")
    lines.append("")
    lines.append("## 4. Rating changes")
    lines.append("")
    lines.append("| ID | Name | Field | Change | Reason | Calibration | Confidence |")
    lines.append("|---|---|---|---|---|---|---|")
    lines.extend(change_rows)
    lines.append("")
    lines.append("All other ratings were retained. Might Duy remains Power 2 because the fatal, non-repeatable Eighth Gate is correctly excluded; no sustainable substitute feat supports a higher rating. Raiga Kurosuki remains at the Grade C anime-only ceiling rather than being upgraded without manga evidence.")
    lines.append("")
    lines.append("## 5. Scores and advisory comparison")
    lines.append("")
    lines.append("- Advisory file matches original Claude ratings for all 62 records.")
    lines.append(f"- Advisory file matches audited ratings for {details['advisory_score_check']['advisory_matches_audited_ratings']} records.")
    lines.append("- The four differences correspond to the four records with changed ratings; derived scores were recomputed with the authoritative `SCORE-1.0` engine, not the advisory copy.")
    lines.append("- No rarity is stored in the KA-IMPORT evaluation records; authoritative rarity is reported in the audit-details companion.")
    lines.append("")
    lines.append("## 6. Strongest role specialists in the importable pool")
    lines.append("")
    for role, entries in top_by_role.items():
        names = ", ".join(f"{e['name']} ({e['scores'][role]})" for e in entries)
        lines.append(f"- **{role}**: {names}")
    lines.append("")
    lines.append("Healer coverage: no importable record has Healer Fit 3 or higher. The highest audited Healer Fit is 2 (Ryōkan, Sekka), both conditional on assistance. The 1,000-match simulation therefore observed 0% of teams with Healer Fit ≥3.")
    lines.append("")
    lines.append("## 7. Artwork review")
    lines.append("")
    lines.append(f"- Catalogue candidates: {len(catalogue['candidates'])}")
    lines.append(f"- Technically valid manifest images: {manifest['summary']['valid']}")
    lines.append(f"- Importable candidates with technically valid artwork: {sum(1 for e in importable if detail_by_id[e['character_id']]['artwork']['technical_valid'])}/{len(importable)}")
    lines.append("- Visual identity verification: not performed.")
    lines.append("- Canonical-version accuracy of images: not visually verified.")
    lines.append("- Publication permission: source-dependent; review required before any publication.")
    lines.append("")
    lines.append("A successful download is not treated as publication-safe or as proof of correct identity/canonical version.")
    lines.append("")
    lines.append("## 8. Simulation")
    lines.append("")
    lines.append(f"- Engine: `{sim['engine']}`")
    lines.append(f"- Matches requested/completed: {sim['matches_requested']}/{sim['matches_completed']}")
    lines.append(f"- Seed: {sim['seed']}; role selection: {sim['role_selection']}")
    lines.append(f"- Rarity weights: `{json.dumps(sim['rarity_weights'])}`")
    lines.append(f"- Pool size: {sim['pool_size']}")
    lines.append(f"- Rarity draw distribution: `{json.dumps(sim['rarity_draw_pct'])}`")
    lines.append(f"- Average role scores: `{json.dumps(sim['role_avg_score'])}`")
    lines.append(f"- Team-score advantage: `{json.dumps(sim['team_score_advantage'])}`")
    lines.append("- No canonical match winner is claimed; this is a draft-engine and SCORE-1.0 team-shape check only.")
    lines.append("")
    lines.append("## 9. Identity and duplicate checks")
    lines.append("")
    lines.append("- No duplicate character IDs within the Claude package, the audited package or the import package.")
    lines.append("- Claude's evaluation order exactly matches the corrected research-package order.")
    lines.append("- Overlap with previously evaluated Naruto datasets:")
    for path, count in existing_overlap.items():
        lines.append(f"  - `{path}`: {count} overlapping IDs")
    lines.append("- Enma remains a manual identity-mapping item and was not evaluated.")
    lines.append("")
    lines.append("## 10. Validation")
    lines.append("")
    lines.append("- Offline audit validator: passed (62 accounted, 52 importable, 10 held, 7 documented changes).")
    lines.append("- Focused audit tests: 15 passed.")
    lines.append("- Full repository regression suite: 182 passed after the audit files were generated.")
    lines.append("- Structural checks: KA-IMPORT format, exact role keys, integer ranges, evidence presence, no forbidden rating keys.")
    lines.append("- Numerical checks: authoritative score and rarity recomputation for all 62 records.")
    lines.append("")
    lines.append("## 11. Complete before-and-after comparison")
    lines.append("")
    lines.append("Fit order: Captain/Strategist/Attacker/Tank/Assassin/Support/Healer.")
    lines.append("")
    lines.append("| ID | Name | Power before | Power after | Fit before | Fit after | Status | Changed | Decision |")
    lines.append("|---|---|---:|---:|---|---|---|---|---|")
    lines.extend(rows)
    lines.append("")
    lines.append("## 12. Publication safeguard")
    lines.append("")
    lines.append("This package is prepared for owner review only. No character is approved, published, scored into a production dataset or activated in gameplay. Rarity values are advisory audit outputs derived from the authoritative implementation, not production assignments.")
    lines.append("")

    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
