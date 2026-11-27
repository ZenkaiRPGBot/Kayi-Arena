# Naruto Simulation Integrity Audit Report

## 1. Finding

The reported inconsistency is caused by **metric labelling and denominator errors**, not by invalid drafting or resolution data.

- The previous report's `Mean team score` was actually the **combined score of both teams** (14 assigned roles, maximum 1400), but it was labelled and compared as if it were one team (7 roles, maximum 700).
- The previous report's `average_assigned_role_scores` divided sums over both teams' 14 assignments per match by only the 7 per-role matchups per match, doubling every value and producing impossible averages above 100.
- The Fit 0 assignment rate was arithmetically correct (14 assignments per completed match) but its denominator was not stated, making the bound check ambiguous.
- Percentiles were computed on combined scores and mislabelled as team percentiles.

The underlying draft engine and RES-1.0 fast-path resolution were correct. The fast path was already cross-checked against authoritative `resolve_match` for outcome, tiebreaker and matchup winners; the corrected run additionally cross-checks team score totals.

## 2. Why the stated bound did not apply

The owner's bound `700 − (7 × 0.1434 × 50) = 649.81` assumes:

1. one team has 7 roles and a 700-point maximum;
2. every Fit 0 role contributes up to 50 points;
3. the reported 693.11 describes one team.

Under actual SCORE-1.0 configuration, Fit 0 role score = `Power × power_points`, and `power_points` is role-specific (captain 8, attacker/tank 5, assassin 7, strategist/support/healer 3). The maximum Fit 0 contribution is therefore at most 40, not 50. More importantly, 693.11 was the combined two-team total, so the correct maximum is 1400. The observed value is fully compatible with the Fit 0 rate once the label is corrected.

## 3. Before and after

| Dataset | Old label/value | Correct label/value | Explanation |
|---|---|---|---|
| A | Mean team score 693.11 | Mean combined match score 693.11; mean per-team score 346.55 | Old value was the sum of both teams (14 roles). |
| A | Average role scores up to 137.53 | Average role scores max 68.76 | Old denominator was 7 matchups/match; correct denominator is 14 assignments/match. |
| A | Team p10 615 | Per-team p10 290; combined p10 not separately reported | Old percentile used combined team totals. |
| A | Fit 0 14.34% | Fit 0 14.34% | Rate unchanged; denominator now explicitly defined. |
| B | Mean team score 630.38 | Mean combined match score 630.38; mean per-team score 315.19 | Old value was the sum of both teams (14 roles). |
| B | Average role scores up to 122.18 | Average role scores max 61.09 | Old denominator was 7 matchups/match; correct denominator is 14 assignments/match. |
| B | Team p10 536 | Per-team p10 249; combined p10 not separately reported | Old percentile used combined team totals. |
| B | Fit 0 18.56% | Fit 0 18.56% | Rate unchanged; denominator now explicitly defined. |
| C | Mean team score 618.12 | Mean combined match score 618.12; mean per-team score 309.06 | Old value was the sum of both teams (14 roles). |
| C | Average role scores up to 119.9 | Average role scores max 59.95 | Old denominator was 7 matchups/match; correct denominator is 14 assignments/match. |
| C | Team p10 518 | Per-team p10 238; combined p10 not separately reported | Old percentile used combined team totals. |
| C | Fit 0 21.14% | Fit 0 21.14% | Rate unchanged; denominator now explicitly defined. |

## 4. Recalculated invariant checks

| Dataset | Matches | Max role score | Max team score | 14-assignment matches | Team-sum verified | Crosscheck outcome | Crosscheck totals |
|---|---:|---:|---:|---:|---:|---:|---:|
| A | 20000 | 100 | 574 | 20000 | 20000 | 100.0% | 100.0% |
| B | 20000 | 100 | 553 | 20000 | 20000 | 100.0% | 100.0% |
| C | 20000 | 100 | 577 | 20000 | 20000 | 100.0% | 100.0% |

All corrected role scores are within 0–100, all per-team scores within 0–700, and every completed match contains exactly 14 assignments whose scores sum to the authoritative team totals.

## 5. Healer metric distinctions

| Dataset | Fit≥3 roster count | Fit≥3 roster share | Teams with healer Fit≥3 | Mean assigned healer Fit |
|---|---:|---:|---:|---:|
| A | 4 | 7.55% | 5.35% | 0.245 |
| B | 10 | 5.43% | 5.77% | 0.265 |
| C | 10 | 4.24% | 5.59% | 0.267 |

Absolute specialist count, roster proportion and actual in-draft acquisition rate are distinct metrics. Fit 0 assignments are also distinct from genuinely low-value assignments: the latter are defined here as role score <50, regardless of Fit label.

## 6. Corrected outcomes

| Dataset | Per-team mean | Combined mean | Fit 0% | Low-value% | Healer Fit≥3 teams% | Player 1% | Draw% |
|---|---:|---:|---:|---:|---:|---:|---:|
| A | 346.55 | 693.11 | 14.34 | 46.41 | 5.35 | 49.91 | 0.2 |
| B | 315.19 | 630.38 | 18.56 | 56.58 | 5.77 | 49.83 | 0.2 |
| C | 309.06 | 618.12 | 21.14 | 57.06 | 5.59 | 50.3 | 0.09 |

## 7. Actions taken

- Preserved the previous simulation JSON and report as `naruto_cumulative_balance_simulation_previous.json` and `NARUTO_CUMULATIVE_BALANCE_REPORT_PREVIOUS.md`.
- Re-ran 20,000 completed matches per dataset with identical reproducible seeds and strategy.
- Rewrote the cumulative balance report with corrected labels, denominators, percentiles and healer distinctions.
- Added regression tests for score bounds, team-sum equality, assignment counts, denominators, percentiles and aggregate bounds.
- Did not modify any character rating, rarity probability, gameplay mechanic or audited evaluation.
