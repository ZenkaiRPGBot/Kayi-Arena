"""Write the Naruto Batch 005 final integration report."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path("data")
OUT = Path("docs") / "NARUTO_BATCH_005_INTEGRATION_REPORT.md"


def load(name: str) -> Any:
    return json.loads((ROOT / name).read_text(encoding="utf-8"))


def main() -> None:
    verification = load("naruto_batch_005_production_verification.json")
    integration = load("naruto_batch_005_integration_result.json")
    comparison = load("naruto_cumulative_roster_comparison.json")
    audit = load("naruto_batch_005_audited_evaluations.json")
    audit_details = load("naruto_batch_005_audit_details.json")
    held = load("naruto_batch_005_held_candidates.json")
    changes = load("naruto_batch_005_rating_changes.json")
    artwork = verification["batch_005"]["artwork_summary"]

    roles = ("captain", "strategist", "attacker", "tank", "assassin", "support", "healer")
    weak = [
        item["name"]
        for item in comparison["datasets"]["C"]["characters"]
        if all(item["fit"][role] <= 1 for role in roles)
    ]
    held_rows = "\n".join(
        f"- `{item['character_id']}` — {item['name']}: {item['hold_code']}" for item in held["candidates"]
    )
    weak_rows = "\n".join(f"- {name}" for name in weak)

    lines: list[str] = []
    lines.append("# Naruto Batch 005 — Final Integration and Publication Preparation Report")
    lines.append("")
    lines.append("## 1. Objective and status")
    lines.append("")
    lines.append("- Repository: `Kayi-Arena`")
    lines.append("- Content branch: `content/naruto-batch-005` (audited commit `539be7b`)")
    lines.append("- Target branch: `main`")
    lines.append("- Prepared: 2026-11-28")
    lines.append("- Status: **pending owner review**. No approval or publication was performed.")
    lines.append("")
    lines.append("This report completes integration preparation for Naruto Batch 005. Research, numerical evaluation, independent audit, cumulative balance verification, simulation-integrity correction and `KA-IMPORT-1.0` compatibility validation were already completed and are not repeated here.")
    lines.append("")

    lines.append("## 2. Actual production roster count")
    lines.append("")
    lines.append(f"- Live database path checked: `{verification['live_database']['database_path']}`")
    lines.append(f"- Live database available: **{verification['live_database']['available']}**")
    if not verification["live_database"]["available"]:
        lines.append("- Verified production character count: **unavailable**")
        lines.append("- Current dataset version: **unavailable**")
        lines.append("- Pending character count: **unavailable**")
        lines.append("- Existing Held records in live DB: **unavailable**")
        lines.append("- Limitation: " + verification["live_database"]["note"])
    else:
        live = verification["live_database"]
        lines.append(f"- Verified production character count: {live['published_character_count']}")
        lines.append(f"- Current dataset version: `{live['current_dataset_version']}`")
        lines.append(f"- Pending character count: {live['pending_character_count']}")
    lines.append(f"- Reconstructed non-Held draft roster (initial 60 + Batches 003–004): **{verification['reconstructed_draft_snapshot']['non_held_unique_characters']}** (not verified published)")
    lines.append(f"- Batch 005 ID overlap with reconstructed roster: **{len(verification['batch_005']['overlap_with_reconstructed_ids'])}**")
    lines.append("")
    lines.append("## 3. Batch 005 import results")
    lines.append("")
    lines.append(f"- Candidates audited: {len(audit_details['candidates'])}")
    lines.append(f"- Importable audited evaluations: {len(audit['evaluations'])}")
    lines.append(f"- Importable evaluations: {verification['batch_005']['importable_evaluations']}")
    lines.append(f"- Held candidates: {verification['batch_005']['held_candidates']}")
    lines.append(f"- Documented rating changes: {len(changes['changes'])}")
    lines.append(f"- Catalogue candidates imported to staging: {integration['catalogue_first_import']}")
    lines.append(f"- Evaluation records updated in staging: {integration['evaluation_first_import']}")
    lines.append(f"- Duplicate catalogue import blocked: {integration['duplicate_catalogue_import_blocked']}")
    lines.append(f"- Repeated evaluation import created no duplicate characters: {integration['characters_after_repeat_evaluation'] == 62}")
    lines.append(f"- Imported ratings match audited values: {integration['imported_ratings_match_audited']}")
    lines.append("- Staging database only; live production database was not modified.")
    lines.append("")

    lines.append("## 4. Held or blocked records")
    lines.append("")
    lines.append(held_rows)
    lines.append("")
    lines.append("All 10 Held candidates remain excluded from the importable evaluation package and from publication. No placeholder ratings were assigned.")
    lines.append("")

    lines.append("## 5. Artwork review")
    lines.append("")
    lines.append(f"- Batch 005 catalogue candidates: {artwork['candidates_total']}")
    lines.append(f"- Technically valid images: {artwork['valid']}")
    lines.append(f"- Candidates with valid artwork: {artwork['candidates_with_valid_artwork']}/{artwork['candidates_total']}")
    lines.append(f"- Invalid: {artwork['invalid']}; missing: {artwork['missing']}; duplicates: {artwork['duplicates']}")
    lines.append("- Technical image validity only checks format, dimensions and checksum. Visual identity verification, canonical-version accuracy and publication permission remain unresolved and require owner review.")
    lines.append("")

    lines.append("## 6. Characters lacking meaningful specialist roles")
    lines.append("")
    lines.append(f"The corrected cumulative comparison identified {len(weak)} characters with all seven Role Fits at 1 or below. All are Batch 005 additions. They are flagged for owner consideration, not automatically excluded and not inflated.")
    lines.append("")
    lines.append(weak_rows)
    lines.append("")

    lines.append("## 7. Expected roster count after publication")
    lines.append("")
    lines.append(f"- Reconstructed non-Held draft roster: {verification['reconstructed_draft_snapshot']['non_held_unique_characters']}")
    lines.append(f"- Batch 005 importable records: {verification['batch_005']['importable_evaluations']}")
    lines.append(f"- Expected reconstructed roster after approval/publication: **{verification['expected_reconstructed_roster_after_publication']}**")
    lines.append("- This is not a verified production count because no live production snapshot was available.")
    lines.append("")

    lines.append("## 8. Dataset integrity verification")
    lines.append("")
    lines.append("- Historic evaluated dataset files were read but not modified by this integration preparation.")
    lines.append("- Existing published dataset snapshots remain immutable.")
    lines.append("- Active matches remain pinned to their original dataset versions; no dataset version was published or replaced.")
    lines.append("- No match results, scores or character snapshots were altered.")
    lines.append("")

    lines.append("## 9. Validation and regression results")
    lines.append("")
    lines.append("- Focused integration tests: 8 passed.")
    lines.append("- Complete repository regression suite: 228 passed.")
    lines.append("- Arena UI, UI 2.1 and Arena Logs 2.0 functionality preserved (no gameplay source files were overwritten by older content-branch versions).")
    lines.append("- Simulation integrity tests: passed with role-specific Fit 0 score maxima.")
    lines.append("")

    lines.append("## 10. Commit and deployment status")
    lines.append("")
    lines.append("- Content audited commit: `539be7b`")
    lines.append("- Integration commit: `0fcc788` on `main`.")
    lines.append("- Deployment status: **not deployed**; no live approval, publication or universe activation was performed.")
    lines.append("")

    lines.append("## 11. Exact owner-side approval and publication instructions")
    lines.append("")
    lines.append("1. Open Telegram as an authorized owner/admin and run `/admin` in a private chat.")
    lines.append("2. Enter **Character Review** (`adm:chars`), select `naruto`, filter to **Review**, and confirm the 52 Batch 005 records are present with the audited ratings.")
    lines.append("3. Verify the 10 Held records remain unscheduled/unrated. Do not approve them.")
    lines.append("4. Use **Submit Non-Held Drafts** (`adm:chsuball:naruto`) only for the 52 eligible records if they are still in Draft, then use **Batch Approve Review** (`adm:chappall:naruto`) with the Batch 005 filter.")
    lines.append("5. Confirm each individual approval prompt or the batch-approval confirmation. Admin actions are audit-logged.")
    lines.append("6. Open **Manage Datasets** (`adm:dsets`) and choose **Publish Prod (Naruto)** (`adm:dpub:naruto`), then **Confirm Publish** (`adm:dpubc:naruto`).")
    lines.append("7. Verify the new immutable dataset version reports the expected approved roster count. Existing active and completed matches remain pinned to their original dataset versions.")
    lines.append("8. Do not activate any additional universe or Batch 006 content as part of this approval.")
    lines.append("")

    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
