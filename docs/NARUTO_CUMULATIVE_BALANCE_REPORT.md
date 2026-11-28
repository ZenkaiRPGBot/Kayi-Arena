# Naruto Cumulative Balance Verification Report — Corrected

## 1. Status and correction note

- Branch: `content/naruto-batch-005`
- Corrected simulation commit: pending publication
- Canonical policy: `NARUTO-CANON-0.1`; scoring `SCORE-1.0`; rarity `RARITY-0.2`
- Prepared: 2026-11-27
- Status: **analysis and integration preparation only**; no approval or publication.

This report supersedes `NARUTO_CUMULATIVE_BALANCE_REPORT_PREVIOUS.md`, which is preserved for audit. The previous report used a combined two-team score but labelled it as a single-team score, and divided per-role score sums by matchup counts instead of assignment counts. See `NARUTO_SIMULATION_INTEGRITY_AUDIT_REPORT.md` for the full investigation.

## 2. Dataset construction

No exact verified published production snapshot is present in the repository. Datasets A/B/C are reconstructed from draft evaluation snapshots, with Held records excluded.

| Dataset | Description | Verified published snapshot | Characters | Held excluded | Duplicates removed |
|---|---|---|---:|---:|---:|
| A | Reconstructed current Naruto roster from the initial 60 draft evaluation snapshot. | False | 53 | 7 | 0 |
| B | Dataset A plus eligible Batches 003-004 draft characters. | False | 184 | 24 | 0 |
| C | Dataset B plus the 52 audited Batch 005 importable characters. | False | 236 | 34 | 0 |

## 3. Distribution comparison

| Metric | A | B | C | C − B |
|---|---:|---:|---:|---:|
| Power 1 | 0 | 11 | 47 | +36 |
| Power 2 | 2 | 52 | 66 | +14 |
| Power 3 | 20 | 84 | 86 | +2 |
| Power 4 | 26 | 32 | 32 | +0 |
| Power 5 | 5 | 5 | 5 | +0 |
| Common | 0 | 59 | 109 | +50 |
| Uncommon | 19 | 83 | 85 | +2 |
| Rare | 25 | 32 | 32 | +0 |
| Epic | 2 | 3 | 3 | +0 |
| Legendary | 7 | 7 | 7 | +0 |
| No meaningful specialist role | 0 | 0 | 33 | +33 |
| Support Fit≥3 | 23 | 52 | 53 | +1 |
| Strategist Fit≥3 | 27 | 51 | 51 | +0 |

### Healer specialist availability (absolute and proportional)

| Healer threshold | A count | B count | C count | C share |
|---|---:|---:|---:|---:|
| Fit≥1 | 6 | 18 | 22 | 9.32% |
| Fit≥2 | 4 | 14 | 16 | 6.78% |
| Fit≥3 | 4 | 10 | 10 | 4.24% |
| Fit≥4 | 3 | 4 | 4 | 1.69% |
| Fit≥5 | 1 | 1 | 1 | 0.42% |

## 4. Simulation methodology

- Engine: `app.engine + RES-1.0 fast path cross-checked with app.resolution.resolve_match`
- Matches per dataset: 20000
- Seeds: draw `20261201`, role assignment `20261202`
- Strategy: uniform random role from remaining roles; skip the first Common draw per player when a non-Common character remains and skips are available
- Resolution: canonical RES-1.0 fast path, cross-checked against app.resolution.resolve_match for outcome, tiebreaker, matchup winners and team score totals
- Denominator: one role assignment; 14 assignments per completed match.
- Team score: seven assigned roles, maximum 700. Combined match score: 14 assigned roles, maximum 1400.
- Simulated strategies do not represent human behavior.

## 5. Corrected simulation results

| Metric | A | B | C |
|---|---:|---:|---:|
| Pool size | 53 | 184 | 236 |
| Matches completed | 20000 | 20000 | 20000 |
| Draft completion % | 100.0 | 100.0 | 100.0 |
| Mean team score /700 | 346.55 | 315.19 | 309.06 |
| Team score p10 | 290 | 249 | 238 |
| Team score p50 | 345 | 314 | 309 |
| Team score p90 | 405 | 382 | 380 |
| Mean combined match score /1400 | 693.11 | 630.38 | 618.12 |
| Mean assigned healer Fit | 0.245 | 0.265 | 0.267 |
| Teams with healer Fit≥3 % | 5.35 | 5.77 | 5.59 |
| Teams with healer Fit≥4 % | 3.98 | 3.46 | 3.72 |
| Fit 0 assignment rate % | 14.34 | 18.56 | 21.14 |
| Fit≤1 assignment rate % | 36.33 | 42.41 | 44.13 |
| Low-value (score<50) rate % | 46.41 | 56.58 | 57.06 |
| Skips used | 0 | 67099 | 67135 |
| Player 1 win % | 49.91 | 49.83 | 50.3 |
| Player 2 win % | 49.88 | 49.98 | 49.61 |
| Draw % | 0.2 | 0.2 | 0.09 |
| Decided by matchup count % | 83.81 | 86.16 | 86.48 |
| Decided by combined score % | 15.98 | 13.64 | 13.43 |

### Average assigned role scores (correct denominator)

| Role | A | B | C |
|---|---:|---:|---:|
| captain | 54.8 | 49.39 | 48.72 |
| strategist | 53.77 | 50.65 | 49.12 |
| attacker | 68.76 | 61.09 | 59.95 |
| tank | 60.13 | 52.15 | 51.15 |
| assassin | 46.24 | 41.42 | 40.53 |
| support | 48.4 | 46.62 | 45.8 |
| healer | 14.45 | 13.87 | 13.8 |

### Rarity draw distribution

| Rarity | A % | B % | C % |
|---|---:|---:|---:|
| Common | 0.0 | 30.5 | 30.51 |
| Uncommon | 46.09 | 30.54 | 30.5 |
| Rare | 33.94 | 22.44 | 22.45 |
| Epic | 12.22 | 11.42 | 11.45 |
| Legendary | 7.74 | 5.1 | 5.1 |

## 6. Corrected Batch 005 impact

- Mean team score: 315.19 (B) → 309.06 (C), -6.13.
- Fit 0 assignments: 18.56% → 21.14%.
- Low-value assignments (score <50): 56.58% → 57.06%.
- Teams with healer Fit≥3: 5.77% → 5.59%.
- Healer Fit≥3 roster count: 10 → 10 (no additional Fit≥3 healer).
- Player 1 win rate: 49.83% → 50.3%.

Interpretation: Batch 005 broadens the pool with predominantly Common, low-Power utility characters. It lowers average team strength and increases Fit 0 / low-value assignments, while adding no Fit≥3 healer. No rating inflation or rarity-probability change is recommended.

## 7. Integration readiness

- Schema: `KA-IMPORT-1.0`
- Catalogue IDs imported: 62
- Importable evaluations: 52
- Held candidates preserved: 10
- No Batch 005 overlap with existing datasets: True
- Recommendation: Import-ready from a schema and identity perspective. Owner approval and visual/canonical artwork review are still required before production publication.

## 8. Limitations

- No verified published production snapshot was available; A/B/C are reconstructed draft snapshots.
- Simulated behavior is deterministic and not human behavior.
- Artwork visual identity and publication permission remain unresolved.
- No owner approval or production publication was performed.

## 9. Validation

- Simulation integrity regression suite: passed.
- Complete repository regression suite: passed after correction.
