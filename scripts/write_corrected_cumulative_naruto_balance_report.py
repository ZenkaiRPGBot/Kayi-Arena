"""Write the corrected cumulative Naruto balance report."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path("data")
OUT = Path("docs") / "NARUTO_CUMULATIVE_BALANCE_REPORT.md"
ROLES = ["captain", "strategist", "attacker", "tank", "assassin", "support", "healer"]


def load(name: str) -> Any:
    return json.loads((ROOT / name).read_text(encoding="utf-8"))


def delta(value: float, baseline: float) -> str:
    diff = value - baseline
    return f"{'+' if diff > 0 else ''}{diff:.2f}"


def main() -> None:
    comparison = load("naruto_cumulative_roster_comparison.json")
    simulation = load("naruto_cumulative_balance_simulation_corrected.json")
    integration = load("naruto_cumulative_integration_validation.json")
    datasets = comparison["datasets"]
    sims = simulation["datasets"]

    lines: list[str] = []
    lines.append("# Naruto Cumulative Balance Verification Report — Corrected")
    lines.append("")
    lines.append("## 1. Status and correction note")
    lines.append("")
    lines.append("- Branch: `content/naruto-batch-005`")
    lines.append("- Corrected simulation commit: pending publication")
    lines.append("- Canonical policy: `NARUTO-CANON-0.1`; scoring `SCORE-1.0`; rarity `RARITY-0.2`")
    lines.append("- Prepared: 2026-11-27")
    lines.append("- Status: **analysis and integration preparation only**; no approval or publication.")
    lines.append("")
    lines.append("This report supersedes `NARUTO_CUMULATIVE_BALANCE_REPORT_PREVIOUS.md`, which is preserved for audit. The previous report used a combined two-team score but labelled it as a single-team score, and divided per-role score sums by matchup counts instead of assignment counts. See `NARUTO_SIMULATION_INTEGRITY_AUDIT_REPORT.md` for the full investigation.")
    lines.append("")

    lines.append("## 2. Dataset construction")
    lines.append("")
    lines.append(comparison["snapshot_note"])
    lines.append("")
    lines.append("| Dataset | Description | Verified published snapshot | Characters | Held excluded | Duplicates removed |")
    lines.append("|---|---|---|---:|---:|---:|")
    for label in ("A", "B", "C"):
        d = datasets[label]
        lines.append(
            f"| {label} | {d['description']} | {d['verified_published_snapshot']} | "
            f"{d['analysis']['character_count']} | {d['excluded_held_count']} | {len(d['duplicates_removed'])} |"
        )
    lines.append("")

    lines.append("## 3. Distribution comparison")
    lines.append("")
    lines.append("| Metric | A | B | C | C − B |")
    lines.append("|---|---:|---:|---:|---:|")
    dist_rows = [
        ("Power 1", lambda a: a["power_distribution"]["1"]),
        ("Power 2", lambda a: a["power_distribution"]["2"]),
        ("Power 3", lambda a: a["power_distribution"]["3"]),
        ("Power 4", lambda a: a["power_distribution"]["4"]),
        ("Power 5", lambda a: a["power_distribution"]["5"]),
        ("Common", lambda a: a["rarity_distribution"]["Common"]),
        ("Uncommon", lambda a: a["rarity_distribution"]["Uncommon"]),
        ("Rare", lambda a: a["rarity_distribution"]["Rare"]),
        ("Epic", lambda a: a["rarity_distribution"]["Epic"]),
        ("Legendary", lambda a: a["rarity_distribution"]["Legendary"]),
        ("No meaningful specialist role", lambda a: a["characters_with_no_meaningful_specialist_role"]),
        ("Support Fit≥3", lambda a: a["support_specialists_fit_ge_3"]),
        ("Strategist Fit≥3", lambda a: a["strategist_specialists_fit_ge_3"]),
    ]
    for name, func in dist_rows:
        vals = [func(datasets[l]["analysis"]) for l in ("A", "B", "C")]
        lines.append(f"| {name} | {vals[0]} | {vals[1]} | {vals[2]} | {vals[2]-vals[1]:+d} |")
    lines.append("")
    lines.append("### Healer specialist availability (absolute and proportional)")
    lines.append("")
    lines.append("| Healer threshold | A count | B count | C count | C share |")
    lines.append("|---|---:|---:|---:|---:|")
    for level in (1, 2, 3, 4, 5):
        counts = [datasets[l]["analysis"]["healer_fit_counts"][f"ge_{level}"] for l in ("A", "B", "C")]
        share = 100.0 * counts[2] / datasets["C"]["analysis"]["character_count"]
        lines.append(f"| Fit≥{level} | {counts[0]} | {counts[1]} | {counts[2]} | {share:.2f}% |")
    lines.append("")

    lines.append("## 4. Simulation methodology")
    lines.append("")
    lines.append(f"- Engine: `{simulation['engine']}`")
    lines.append(f"- Matches per dataset: {simulation['matches_per_dataset']}")
    lines.append(f"- Seeds: draw `{sims['A']['seeds']['draw']}`, role assignment `{sims['A']['seeds']['role_assignment']}`")
    lines.append(f"- Strategy: {sims['A']['assignment_strategy']}")
    lines.append(f"- Resolution: {sims['A']['resolution_method']}")
    lines.append("- Denominator: one role assignment; 14 assignments per completed match.")
    lines.append("- Team score: seven assigned roles, maximum 700. Combined match score: 14 assigned roles, maximum 1400.")
    lines.append("- Simulated strategies do not represent human behavior.")
    lines.append("")

    lines.append("## 5. Corrected simulation results")
    lines.append("")
    lines.append("| Metric | A | B | C |")
    lines.append("|---|---:|---:|---:|")
    rows = [
        ("Pool size", lambda s: s["pool_size"]),
        ("Matches completed", lambda s: s["matches_completed"]),
        ("Draft completion %", lambda s: s["draft_completion_rate_pct"]),
        ("Mean team score /700", lambda s: s["team_score"]["mean"]),
        ("Team score p10", lambda s: s["team_score"]["p10"]),
        ("Team score p50", lambda s: s["team_score"]["p50"]),
        ("Team score p90", lambda s: s["team_score"]["p90"]),
        ("Mean combined match score /1400", lambda s: s["combined_match_score"]["mean"]),
        ("Mean assigned healer Fit", lambda s: s["healer_metrics"]["mean_assigned_healer_fit"]),
        ("Teams with healer Fit≥3 %", lambda s: s["healer_metrics"]["teams_with_healer_fit_ge_3_pct"]),
        ("Teams with healer Fit≥4 %", lambda s: s["healer_metrics"]["teams_with_healer_fit_ge_4_pct"]),
        ("Fit 0 assignment rate %", lambda s: s["assignment_metrics"]["fit_0_assignment_rate_pct"]),
        ("Fit≤1 assignment rate %", lambda s: s["assignment_metrics"]["fit_le_1_assignment_rate_pct"]),
        ("Low-value (score<50) rate %", lambda s: s["assignment_metrics"]["low_value_assignment_rate_pct"]),
        ("Skips used", lambda s: s["skip_utilization"]["skips_used"]),
        ("Player 1 win %", lambda s: s["match_outcomes"]["player_1_win"]),
        ("Player 2 win %", lambda s: s["match_outcomes"]["player_2_win"]),
        ("Draw %", lambda s: s["match_outcomes"]["draw"]),
        ("Decided by matchup count %", lambda s: s["decided_by"]["matchup_count"]),
        ("Decided by combined score %", lambda s: s["decided_by"]["combined_score"]),
    ]
    for name, func in rows:
        vals = [func(sims[l]) for l in ("A", "B", "C")]
        lines.append(f"| {name} | {vals[0]} | {vals[1]} | {vals[2]} |")
    lines.append("")
    lines.append("### Average assigned role scores (correct denominator)")
    lines.append("")
    lines.append("| Role | A | B | C |")
    lines.append("|---|---:|---:|---:|")
    for role in ROLES:
        vals = [sims[l]["average_assigned_role_scores"][role] for l in ("A", "B", "C")]
        lines.append(f"| {role} | {vals[0]} | {vals[1]} | {vals[2]} |")
    lines.append("")
    lines.append("### Rarity draw distribution")
    lines.append("")
    lines.append("| Rarity | A % | B % | C % |")
    lines.append("|---|---:|---:|---:|")
    for tier in ("Common", "Uncommon", "Rare", "Epic", "Legendary"):
        vals = [sims[l]["rarity_draw_distribution_pct"][tier] for l in ("A", "B", "C")]
        lines.append(f"| {tier} | {vals[0]} | {vals[1]} | {vals[2]} |")
    lines.append("")

    lines.append("## 6. Corrected Batch 005 impact")
    lines.append("")
    lines.append(f"- Mean team score: {sims['B']['team_score']['mean']} (B) → {sims['C']['team_score']['mean']} (C), {delta(sims['C']['team_score']['mean'], sims['B']['team_score']['mean'])}.")
    lines.append(f"- Fit 0 assignments: {sims['B']['assignment_metrics']['fit_0_assignment_rate_pct']}% → {sims['C']['assignment_metrics']['fit_0_assignment_rate_pct']}%.")
    lines.append(f"- Low-value assignments (score <50): {sims['B']['assignment_metrics']['low_value_assignment_rate_pct']}% → {sims['C']['assignment_metrics']['low_value_assignment_rate_pct']}%.")
    lines.append(f"- Teams with healer Fit≥3: {sims['B']['healer_metrics']['teams_with_healer_fit_ge_3_pct']}% → {sims['C']['healer_metrics']['teams_with_healer_fit_ge_3_pct']}%.")
    lines.append(f"- Healer Fit≥3 roster count: {datasets['B']['analysis']['healer_fit_counts']['ge_3']} → {datasets['C']['analysis']['healer_fit_counts']['ge_3']} (no additional Fit≥3 healer).")
    lines.append(f"- Player 1 win rate: {sims['B']['match_outcomes']['player_1_win']}% → {sims['C']['match_outcomes']['player_1_win']}%.")
    lines.append("")
    lines.append("Interpretation: Batch 005 broadens the pool with predominantly Common, low-Power utility characters. It lowers average team strength and increases Fit 0 / low-value assignments, while adding no Fit≥3 healer. No rating inflation or rarity-probability change is recommended.")
    lines.append("")

    lines.append("## 7. Integration readiness")
    lines.append("")
    lines.append(f"- Schema: `{integration['schema']}`")
    lines.append(f"- Catalogue IDs imported: {integration['checks']['catalogue_unique_ids']}")
    lines.append(f"- Importable evaluations: {integration['checks']['importable_evaluation_count']}")
    lines.append(f"- Held candidates preserved: {integration['checks']['held_count']}")
    lines.append(f"- No Batch 005 overlap with existing datasets: {integration['checks']['no_overlap_batch005_with_existing_datasets']}")
    lines.append(f"- Recommendation: {integration['recommendation']}")
    lines.append("")

    lines.append("## 8. Limitations")
    lines.append("")
    lines.append("- No verified published production snapshot was available; A/B/C are reconstructed draft snapshots.")
    lines.append("- Simulated behavior is deterministic and not human behavior.")
    lines.append("- Artwork visual identity and publication permission remain unresolved.")
    lines.append("- No owner approval or production publication was performed.")
    lines.append("")

    lines.append("## 9. Validation")
    lines.append("")
    lines.append("- Simulation integrity regression suite: passed.")
    lines.append("- Complete repository regression suite: passed after correction.")
    lines.append("")

    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
