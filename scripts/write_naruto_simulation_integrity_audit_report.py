"""Write the explicit Naruto simulation integrity audit report."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path("data")
OUT = Path("docs") / "NARUTO_SIMULATION_INTEGRITY_AUDIT_REPORT.md"


def load(name: str) -> Any:
    return json.loads((ROOT / name).read_text(encoding="utf-8"))


def main() -> None:
    previous = load("naruto_cumulative_balance_simulation_previous.json")["datasets"]
    corrected = load("naruto_cumulative_balance_simulation_corrected.json")["datasets"]

    lines: list[str] = []
    lines.append("# Naruto Simulation Integrity Audit Report")
    lines.append("")
    lines.append("## 1. Finding")
    lines.append("")
    lines.append("The reported inconsistency is caused by **metric labelling and denominator errors**, not by invalid drafting or resolution data.")
    lines.append("")
    lines.append("- The previous report's `Mean team score` was actually the **combined score of both teams** (14 assigned roles, maximum 1400), but it was labelled and compared as if it were one team (7 roles, maximum 700).")
    lines.append("- The previous report's `average_assigned_role_scores` divided sums over both teams' 14 assignments per match by only the 7 per-role matchups per match, doubling every value and producing impossible averages above 100.")
    lines.append("- The Fit 0 assignment rate was arithmetically correct (14 assignments per completed match) but its denominator was not stated, making the bound check ambiguous.")
    lines.append("- Percentiles were computed on combined scores and mislabelled as team percentiles.")
    lines.append("")
    lines.append("The underlying draft engine and RES-1.0 fast-path resolution were correct. The fast path was already cross-checked against authoritative `resolve_match` for outcome, tiebreaker and matchup winners; the corrected run additionally cross-checks team score totals.")
    lines.append("")

    lines.append("## 2. Why the stated bound did not apply")
    lines.append("")
    lines.append("The owner's bound `700 − (7 × 0.1434 × 50) = 649.81` assumes:")
    lines.append("")
    lines.append("1. one team has 7 roles and a 700-point maximum;")
    lines.append("2. every Fit 0 role contributes up to 50 points;")
    lines.append("3. the reported 693.11 describes one team.")
    lines.append("")
    lines.append("Under actual SCORE-1.0 configuration, Fit 0 role score = `Power × power_points`, and `power_points` is role-specific (captain 8, attacker/tank 5, assassin 7, strategist/support/healer 3). The maximum Fit 0 contribution is therefore at most 40, not 50. More importantly, 693.11 was the combined two-team total, so the correct maximum is 1400. The observed value is fully compatible with the Fit 0 rate once the label is corrected.")
    lines.append("")

    lines.append("## 3. Before and after")
    lines.append("")
    lines.append("| Dataset | Old label/value | Correct label/value | Explanation |")
    lines.append("|---|---|---|---|")
    for label in ("A", "B", "C"):
        old = previous[label]
        new = corrected[label]
        lines.append(
            f"| {label} | Mean team score {old['team_score']['mean']} | "
            f"Mean combined match score {new['combined_match_score']['mean']}; "
            f"mean per-team score {new['team_score']['mean']} | "
            "Old value was the sum of both teams (14 roles). |"
        )
        lines.append(
            f"| {label} | Average role scores up to {max(old['average_assigned_role_scores'].values())} | "
            f"Average role scores max {max(new['average_assigned_role_scores'].values())} | "
            "Old denominator was 7 matchups/match; correct denominator is 14 assignments/match. |"
        )
        lines.append(
            f"| {label} | Team p10 {old['team_score']['p10']} | "
            f"Per-team p10 {new['team_score']['p10']}; combined p10 not separately reported | "
            "Old percentile used combined team totals. |"
        )
        lines.append(
            f"| {label} | Fit 0 {old['weak_or_unusable_assignments']['fit_0_pct']}% | "
            f"Fit 0 {new['assignment_metrics']['fit_0_assignment_rate_pct']}% | "
            "Rate unchanged; denominator now explicitly defined. |"
        )
    lines.append("")

    lines.append("## 4. Recalculated invariant checks")
    lines.append("")
    lines.append("| Dataset | Matches | Max role score | Max team score | 14-assignment matches | Team-sum verified | Crosscheck outcome | Crosscheck totals |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|---:|")
    for label in ("A", "B", "C"):
        d = corrected[label]
        v = d["verification"]
        c = d["resolution_crosscheck"]
        lines.append(
            f"| {label} | {d['matches_completed']} | {v['maximum_role_score_observed']} | "
            f"{v['maximum_team_score_observed']} | {v['completed_matches_with_exactly_14_assignments']} | "
            f"{v['completed_matches_with_verified_team_sums']} | {c['identical_pct']}% | {c['score_identical_pct']}% |"
        )
    lines.append("")
    lines.append("All corrected role scores are within 0–100, all per-team scores within 0–700, and every completed match contains exactly 14 assignments whose scores sum to the authoritative team totals.")
    lines.append("")

    lines.append("## 5. Healer metric distinctions")
    lines.append("")
    lines.append("| Dataset | Fit≥3 roster count | Fit≥3 roster share | Teams with healer Fit≥3 | Mean assigned healer Fit |")
    lines.append("|---|---:|---:|---:|---:|")
    for label in ("A", "B", "C"):
        h = corrected[label]["healer_metrics"]
        lines.append(
            f"| {label} | {h['roster_absolute']['fit_ge_3']} | "
            f"{h['roster_proportion_pct']['fit_ge_3']}% | "
            f"{h['teams_with_healer_fit_ge_3_pct']}% | "
            f"{h['mean_assigned_healer_fit']} |"
        )
    lines.append("")
    lines.append("Absolute specialist count, roster proportion and actual in-draft acquisition rate are distinct metrics. Fit 0 assignments are also distinct from genuinely low-value assignments: the latter are defined here as role score <50, regardless of Fit label.")
    lines.append("")

    lines.append("## 6. Corrected outcomes")
    lines.append("")
    lines.append("| Dataset | Per-team mean | Combined mean | Fit 0% | Low-value% | Healer Fit≥3 teams% | Player 1% | Draw% |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|---:|")
    for label in ("A", "B", "C"):
        d = corrected[label]
        lines.append(
            f"| {label} | {d['team_score']['mean']} | {d['combined_match_score']['mean']} | "
            f"{d['assignment_metrics']['fit_0_assignment_rate_pct']} | "
            f"{d['assignment_metrics']['low_value_assignment_rate_pct']} | "
            f"{d['healer_metrics']['teams_with_healer_fit_ge_3_pct']} | "
            f"{d['match_outcomes']['player_1_win']} | {d['match_outcomes']['draw']} |"
        )
    lines.append("")

    lines.append("## 7. Actions taken")
    lines.append("")
    lines.append("- Preserved the previous simulation JSON and report as `naruto_cumulative_balance_simulation_previous.json` and `NARUTO_CUMULATIVE_BALANCE_REPORT_PREVIOUS.md`.")
    lines.append("- Re-ran 20,000 completed matches per dataset with identical reproducible seeds and strategy.")
    lines.append("- Rewrote the cumulative balance report with corrected labels, denominators, percentiles and healer distinctions.")
    lines.append("- Added regression tests for score bounds, team-sum equality, assignment counts, denominators, percentiles and aggregate bounds.")
    lines.append("- Did not modify any character rating, rarity probability, gameplay mechanic or audited evaluation.")
    lines.append("")

    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
