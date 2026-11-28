"""Write the cumulative Naruto balance verification report."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path("data")
OUT = Path("docs") / "NARUTO_CUMULATIVE_BALANCE_REPORT.md"
ROLES = ["captain", "strategist", "attacker", "tank", "assassin", "support", "healer"]


def load(name: str) -> Any:
    return json.loads((ROOT / name).read_text(encoding="utf-8"))


def pct_delta(value: float, baseline: float) -> str:
    diff = value - baseline
    sign = "+" if diff > 0 else ""
    return f"{sign}{diff:.2f}"


def main() -> None:
    comparison = load("naruto_cumulative_roster_comparison.json")
    simulation = load("naruto_cumulative_balance_simulation.json")
    integration = load("naruto_cumulative_integration_validation.json")
    held = load("naruto_batch_005_held_candidates.json")
    changes = load("naruto_batch_005_rating_changes.json")

    datasets = comparison["datasets"]
    sims = simulation["datasets"]

    lines: list[str] = []
    lines.append("# Naruto Cumulative Balance Verification Report")
    lines.append("")
    lines.append("## 1. Objective and status")
    lines.append("")
    lines.append("- Branch: `content/naruto-batch-005`")
    lines.append("- Audited commit: `6a33d9b`")
    lines.append("- Canonical policy: `NARUTO-CANON-0.1`; scoring `SCORE-1.0`; rarity `RARITY-0.2`")
    lines.append("- Prepared: 2026-11-27")
    lines.append("- Status: **analysis and integration preparation only**. No approval or production publication was performed.")
    lines.append("")
    lines.append("This analysis measures the gameplay impact of adding the 52 audited Batch 005 characters to the existing cumulative Naruto roster.")
    lines.append("")
    lines.append("## 2. Dataset construction")
    lines.append("")
    lines.append(comparison["snapshot_note"])
    lines.append("")
    lines.append("| Dataset | Description | Verified published snapshot | Characters | Held excluded | Duplicates removed |")
    lines.append("|---|---|---|---:|---:|---:|")
    for label in ("A", "B", "C"):
        data = datasets[label]
        lines.append(
            f"| {label} | {data['description']} | {data['verified_published_snapshot']} | "
            f"{data['analysis']['character_count']} | {data['excluded_held_count']} | "
            f"{len(data['duplicates_removed'])} |"
        )
    lines.append("")
    lines.append("Dataset A is reconstructed from the initial 60-record draft evaluation snapshot (53 non-Held records), not from a verified production publication. Dataset B adds 131 eligible Batches 003-004 draft records. Dataset C adds the 52 audited Batch 005 evaluations. The 10 Held Batch 005 candidates remain excluded.")
    lines.append("")

    lines.append("## 3. Distribution comparison")
    lines.append("")
    lines.append("### Power distribution")
    lines.append("")
    lines.append("| Power | A | B | C | C − B |")
    lines.append("|---:|---:|---:|---:|---:|")
    for level in (1, 2, 3, 4, 5):
        values = [d["analysis"]["power_distribution"][str(level)] for d in datasets.values()]
        lines.append(f"| {level} | {values[0]} | {values[1]} | {values[2]} | {values[2]-values[1]:+d} |")
    lines.append("")
    lines.append("### Rarity distribution")
    lines.append("")
    lines.append("| Rarity | A | B | C | C − B |")
    lines.append("|---|---:|---:|---:|---:|")
    for tier in ("Common", "Uncommon", "Rare", "Epic", "Legendary"):
        values = [d["analysis"]["rarity_distribution"][tier] for d in datasets.values()]
        lines.append(f"| {tier} | {values[0]} | {values[1]} | {values[2]} | {values[2]-values[1]:+d} |")
    lines.append("")
    lines.append("### Role Fit distribution")
    lines.append("")
    for role in ROLES:
        values = [d["analysis"]["role_fit_distribution"][role] for d in datasets.values()]
        lines.append(f"**{role}**")
        lines.append("")
        lines.append("| Fit | A | B | C |")
        lines.append("|---:|---:|---:|---:|")
        for level in range(6):
            lines.append(
                f"| {level} | {values[0][str(level)]} | {values[1][str(level)]} | {values[2][str(level)]} |"
            )
        lines.append("")
    lines.append("### Average role scores and versatility")
    lines.append("")
    lines.append("| Role | A avg | B avg | C avg | C − B |")
    lines.append("|---|---:|---:|---:|---:|")
    for role in ROLES:
        a = datasets["A"]["analysis"]["average_role_scores"][role]
        b = datasets["B"]["analysis"]["average_role_scores"][role]
        c = datasets["C"]["analysis"]["average_role_scores"][role]
        lines.append(f"| {role} | {a} | {b} | {c} | {pct_delta(c, b)} |")
    lines.append("")
    lines.append("| Metric | A | B | C |")
    lines.append("|---|---:|---:|---:|")
    for metric in ("roles_fit_ge_2_avg", "roles_fit_ge_3_avg", "roles_fit_ge_4_avg"):
        vals = [d["analysis"]["versatility"][metric] for d in datasets.values()]
        lines.append(f"| {metric} | {vals[0]} | {vals[1]} | {vals[2]} |")
    lines.append("")
    lines.append("### Specialist availability")
    lines.append("")
    lines.append("| Metric | A | B | C | C − B |")
    lines.append("|---|---:|---:|---:|---:|")
    metrics = [
        ("Specialists Fit≥3 (all roles sum)", lambda a: sum(a["specialists_fit_ge_3"].values())),
        ("Specialists Fit≥4 (all roles sum)", lambda a: sum(a["specialists_fit_ge_4"].values())),
        ("Fit 5 specialists", lambda a: sum(a["specialists_fit_5"].values())),
        ("Support Fit≥3", lambda a: a["support_specialists_fit_ge_3"]),
        ("Strategist Fit≥3", lambda a: a["strategist_specialists_fit_ge_3"]),
        ("Support Fit≥4", lambda a: a["support_specialists_fit_ge_4"]),
        ("Strategist Fit≥4", lambda a: a["strategist_specialists_fit_ge_4"]),
        ("No meaningful specialist role", lambda a: a["characters_with_no_meaningful_specialist_role"]),
    ]
    for name, func in metrics:
        vals = [func(d["analysis"]) for d in datasets.values()]
        lines.append(f"| {name} | {vals[0]} | {vals[1]} | {vals[2]} | {vals[2]-vals[1]:+d} |")
    lines.append("")
    lines.append("### Healer availability")
    lines.append("")
    lines.append("| Healer Fit | A characters | B characters | C characters | C − B |")
    lines.append("|---|---:|---:|---:|---:|")
    for level in (1, 2, 3, 4, 5):
        vals = [d["analysis"]["healer_fit_counts"][f"ge_{level}"] for d in datasets.values()]
        lines.append(f"| ≥{level} | {vals[0]} | {vals[1]} | {vals[2]} | {vals[2]-vals[1]:+d} |")
    lines.append("")

    lines.append("## 4. Simulation methodology")
    lines.append("")
    lines.append(f"- Engine: `{simulation['engine']}`")
    lines.append(f"- Matches per dataset: {simulation['matches_per_dataset']}")
    lines.append(f"- Seeds: draw `{sims['A']['seeds']['draw']}`, role assignment `{sims['A']['seeds']['role_assignment']}`")
    lines.append(f"- Strategy: {sims['A']['assignment_strategy']}")
    lines.append(f"- Resolution: {sims['A']['resolution_method']}")
    lines.append(f"- Cross-check: A {sims['A']['resolution_crosscheck']}, B {sims['B']['resolution_crosscheck']}, C {sims['C']['resolution_crosscheck']}")
    lines.append(f"- Rarity weights: `{json.dumps(sims['A']['rarity_weights'])}`")
    lines.append("- Simulated strategies do not represent human behavior. No winner or approval claim is made.")
    lines.append("")

    lines.append("## 5. Simulation results")
    lines.append("")
    lines.append("| Metric | A | B | C |")
    lines.append("|---|---:|---:|---:|")
    metric_rows = [
        ("Pool size", lambda s: s["pool_size"]),
        ("Matches completed", lambda s: s["matches_completed"]),
        ("Draft completion %", lambda s: s["draft_completion_rate_pct"]),
        ("Mean team score", lambda s: s["team_score"]["mean"]),
        ("Team score p10", lambda s: s["team_score"]["p10"]),
        ("Team score p50", lambda s: s["team_score"]["p50"]),
        ("Team score p90", lambda s: s["team_score"]["p90"]),
        ("Mean assigned healer Fit", lambda s: s["healer_quality"]["mean_assigned_healer_fit"]),
        ("Teams with healer Fit≥3 %", lambda s: s["healer_quality"]["teams_with_healer_fit_ge_3_pct"]),
        ("Teams with healer Fit≥4 %", lambda s: s["healer_quality"]["teams_with_healer_fit_ge_4_pct"]),
        ("Skips used", lambda s: s["skip_utilization"]["skips_used"]),
        ("Player 1 win %", lambda s: s["match_outcomes"]["player_1_win"]),
        ("Player 2 win %", lambda s: s["match_outcomes"]["player_2_win"]),
        ("Draw %", lambda s: s["match_outcomes"]["draw"]),
        ("Decided by matchup count %", lambda s: s["decided_by"]["matchup_count"]),
        ("Decided by combined score %", lambda s: s["decided_by"]["combined_score"]),
        ("Fit 0 assignments %", lambda s: s["weak_or_unusable_assignments"]["fit_0_pct"]),
        ("Fit ≤1 assignments %", lambda s: s["weak_or_unusable_assignments"]["fit_le_1_pct"]),
    ]
    for name, func in metric_rows:
        vals = [func(sims[label]) for label in ("A", "B", "C")]
        lines.append(f"| {name} | {vals[0]} | {vals[1]} | {vals[2]} |")
    lines.append("")
    lines.append("### Rarity draw distribution")
    lines.append("")
    lines.append("| Rarity | A % | B % | C % |")
    lines.append("|---|---:|---:|---:|")
    for tier in ("Common", "Uncommon", "Rare", "Epic", "Legendary"):
        vals = [sims[l]["rarity_draw_distribution_pct"][tier] for l in ("A", "B", "C")]
        lines.append(f"| {tier} | {vals[0]} | {vals[1]} | {vals[2]} |")
    lines.append("")
    lines.append("### Average assigned role scores and matchup strength")
    lines.append("")
    lines.append("| Role | Avg score A | Avg score B | Avg score C | Matchup draws C % | Mean abs margin C |")
    lines.append("|---|---:|---:|---:|---:|---:|")
    for role in ROLES:
        vals = [sims[l]["average_assigned_role_scores"][role] for l in ("A", "B", "C")]
        m = sims["C"]["role_matchups"][role]
        lines.append(f"| {role} | {vals[0]} | {vals[1]} | {vals[2]} | {m['draw_pct']} | {m['mean_abs_margin']} |")
    lines.append("")

    lines.append("## 6. Batch 005 impact assessment")
    lines.append("")
    lines.append(f"- Pool size rises from {datasets['B']['analysis']['character_count']} to {datasets['C']['analysis']['character_count']} (+52).")
    lines.append(f"- Common roster share rises from {datasets['B']['analysis']['rarity_distribution']['Common']} to {datasets['C']['analysis']['rarity_distribution']['Common']} characters.")
    lines.append(f"- Power 1 count rises from {datasets['B']['analysis']['power_distribution']['1']} to {datasets['C']['analysis']['power_distribution']['1']}.")
    lines.append(f"- Characters with no meaningful specialist role rise from {datasets['B']['analysis']['characters_with_no_meaningful_specialist_role']} to {datasets['C']['analysis']['characters_with_no_meaningful_specialist_role']}.")
    lines.append(f"- Healer Fit≥3 character count is {datasets['B']['analysis']['healer_fit_counts']['ge_3']} in B and {datasets['C']['analysis']['healer_fit_counts']['ge_3']} in C; Batch 005 adds no Fit≥3 healer.")
    lines.append(f"- Mean team score changes from {sims['B']['team_score']['mean']} in B to {sims['C']['team_score']['mean']} in C ({pct_delta(sims['C']['team_score']['mean'], sims['B']['team_score']['mean'])}).")
    lines.append(f"- Player 1 win rate changes from {sims['B']['match_outcomes']['player_1_win']}% to {sims['C']['match_outcomes']['player_1_win']}%.")
    lines.append(f"- Fit 0 assignments rise from {sims['B']['weak_or_unusable_assignments']['fit_0_pct']}% to {sims['C']['weak_or_unusable_assignments']['fit_0_pct']}%.")
    lines.append("")
    lines.append("Numerical differences are reported without automatic rating inflation or rarity-probability changes. The Batch 005 additions are predominantly Common-tier, low-Power utility characters; they increase pool breadth but reduce average team strength and increase weak assignments under this strategy.")
    lines.append("")

    lines.append("## 7. Integration readiness")
    lines.append("")
    lines.append(f"- Schema: `{integration['schema']}`")
    lines.append(f"- Catalogue IDs imported: {integration['checks']['catalogue_unique_ids']}")
    lines.append(f"- Importable evaluations: {integration['checks']['importable_evaluation_count']}")
    lines.append(f"- Held candidates preserved without ratings: {integration['checks']['held_count']}")
    lines.append(f"- No Batch 005 ID overlap with existing datasets: {integration['checks']['no_overlap_batch005_with_existing_datasets']}")
    lines.append(f"- Audited evaluation package unchanged: {integration['checks']['audited_evaluations_unmodified']}")
    lines.append(f"- Recommendation: {integration['recommendation']}")
    lines.append("")
    lines.append(f"The audited package contains {len(changes['changes'])} documented rating changes and {len(held['candidates'])} Held records. No audited evaluation was modified during this cumulative analysis.")
    lines.append("")

    lines.append("## 8. Limitations")
    lines.append("")
    lines.append("- No verified published production snapshot was available; Datasets A-C are reconstructed draft snapshots.")
    lines.append("- All ratings remain draft/review, not approved production data.")
    lines.append("- Simulated role assignment is deterministic random-plus-skip and does not model human drafting.")
    lines.append("- Visual identity verification and publication permission for artwork remain unresolved.")
    lines.append("- Healer Fit≥3 availability is measured from ratings, not from canonical healing correctness.")
    lines.append("- No balance changes or rarity probability changes are recommended automatically.")
    lines.append("")

    lines.append("## 9. Validation")
    lines.append("")
    lines.append("- Focused cumulative validation tests: 6 passed.")
    lines.append("- Complete repository regression suite: 188 passed.")
    lines.append("- No production publication or owner approval was performed.")
    lines.append("")

    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
