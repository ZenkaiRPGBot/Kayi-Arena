# Naruto Cumulative Balance Verification Report

## 1. Objective and status

- Branch: `content/naruto-batch-005`
- Audited commit: `6a33d9b`
- Canonical policy: `NARUTO-CANON-0.1`; scoring `SCORE-1.0`; rarity `RARITY-0.2`
- Prepared: 2026-11-27
- Status: **analysis and integration preparation only**. No approval or production publication was performed.

This analysis measures the gameplay impact of adding the 52 audited Batch 005 characters to the existing cumulative Naruto roster.

## 2. Dataset construction

No exact verified published production snapshot is present in the repository. Datasets A/B/C are reconstructed from draft evaluation snapshots, with Held records excluded.

| Dataset | Description | Verified published snapshot | Characters | Held excluded | Duplicates removed |
|---|---|---|---:|---:|---:|
| A | Reconstructed current Naruto roster from the initial 60 draft evaluation snapshot. | False | 53 | 7 | 0 |
| B | Dataset A plus eligible Batches 003-004 draft characters. | False | 184 | 24 | 0 |
| C | Dataset B plus the 52 audited Batch 005 importable characters. | False | 236 | 34 | 0 |

Dataset A is reconstructed from the initial 60-record draft evaluation snapshot (53 non-Held records), not from a verified production publication. Dataset B adds 131 eligible Batches 003-004 draft records. Dataset C adds the 52 audited Batch 005 evaluations. The 10 Held Batch 005 candidates remain excluded.

## 3. Distribution comparison

### Power distribution

| Power | A | B | C | C − B |
|---:|---:|---:|---:|---:|
| 1 | 0 | 11 | 47 | +36 |
| 2 | 2 | 52 | 66 | +14 |
| 3 | 20 | 84 | 86 | +2 |
| 4 | 26 | 32 | 32 | +0 |
| 5 | 5 | 5 | 5 | +0 |

### Rarity distribution

| Rarity | A | B | C | C − B |
|---|---:|---:|---:|---:|
| Common | 0 | 59 | 109 | +50 |
| Uncommon | 19 | 83 | 85 | +2 |
| Rare | 25 | 32 | 32 | +0 |
| Epic | 2 | 3 | 3 | +0 |
| Legendary | 7 | 7 | 7 | +0 |

### Role Fit distribution

**captain**

| Fit | A | B | C |
|---:|---:|---:|---:|
| 0 | 0 | 40 | 80 |
| 1 | 13 | 69 | 78 |
| 2 | 12 | 30 | 33 |
| 3 | 19 | 32 | 32 |
| 4 | 8 | 12 | 12 |
| 5 | 1 | 1 | 1 |

**strategist**

| Fit | A | B | C |
|---:|---:|---:|---:|
| 0 | 0 | 5 | 43 |
| 1 | 9 | 61 | 74 |
| 2 | 17 | 67 | 68 |
| 3 | 17 | 39 | 39 |
| 4 | 9 | 10 | 10 |
| 5 | 1 | 2 | 2 |

**attacker**

| Fit | A | B | C |
|---:|---:|---:|---:|
| 0 | 0 | 7 | 40 |
| 1 | 1 | 17 | 27 |
| 2 | 2 | 49 | 56 |
| 3 | 22 | 74 | 76 |
| 4 | 22 | 31 | 31 |
| 5 | 6 | 6 | 6 |

**tank**

| Fit | A | B | C |
|---:|---:|---:|---:|
| 0 | 0 | 24 | 70 |
| 1 | 6 | 57 | 60 |
| 2 | 15 | 48 | 50 |
| 3 | 24 | 45 | 46 |
| 4 | 7 | 9 | 9 |
| 5 | 1 | 1 | 1 |

**assassin**

| Fit | A | B | C |
|---:|---:|---:|---:|
| 0 | 3 | 35 | 76 |
| 1 | 20 | 75 | 84 |
| 2 | 17 | 49 | 51 |
| 3 | 6 | 15 | 15 |
| 4 | 6 | 9 | 9 |
| 5 | 1 | 1 | 1 |

**support**

| Fit | A | B | C |
|---:|---:|---:|---:|
| 0 | 0 | 4 | 16 |
| 1 | 21 | 73 | 106 |
| 2 | 9 | 55 | 61 |
| 3 | 16 | 40 | 41 |
| 4 | 7 | 12 | 12 |
| 5 | 0 | 0 | 0 |

**healer**

| Fit | A | B | C |
|---:|---:|---:|---:|
| 0 | 47 | 166 | 214 |
| 1 | 2 | 4 | 6 |
| 2 | 0 | 4 | 6 |
| 3 | 1 | 6 | 6 |
| 4 | 2 | 3 | 3 |
| 5 | 1 | 1 | 1 |

### Average role scores and versatility

| Role | A avg | B avg | C avg | C − B |
|---|---:|---:|---:|---:|
| captain | 58.79 | 40.74 | 34.9 | -5.84 |
| strategist | 54.23 | 41.92 | 34.66 | -7.26 |
| attacker | 72.08 | 54.95 | 47.08 | -7.87 |
| tank | 63.02 | 46.14 | 39.36 | -6.78 |
| assassin | 50.26 | 38.08 | 32.48 | -5.60 |
| support | 47.81 | 40.91 | 36.24 | -4.67 |
| healer | 16.7 | 12.82 | 11.32 | -1.50 |

| Metric | A | B | C |
|---|---:|---:|---:|
| roles_fit_ge_2_avg | 4.7 | 3.54 | 2.87 |
| roles_fit_ge_3_avg | 3.34 | 1.9 | 1.5 |
| roles_fit_ge_4_avg | 1.36 | 0.53 | 0.42 |

### Specialist availability

| Metric | A | B | C | C − B |
|---|---:|---:|---:|---:|
| Specialists Fit≥3 (all roles sum) | 177 | 349 | 353 | +4 |
| Specialists Fit≥4 (all roles sum) | 72 | 98 | 98 | +0 |
| Fit 5 specialists | 11 | 12 | 12 | +0 |
| Support Fit≥3 | 23 | 52 | 53 | +1 |
| Strategist Fit≥3 | 27 | 51 | 51 | +0 |
| Support Fit≥4 | 7 | 12 | 12 | +0 |
| Strategist Fit≥4 | 10 | 12 | 12 | +0 |
| No meaningful specialist role | 0 | 0 | 33 | +33 |

### Healer availability

| Healer Fit | A characters | B characters | C characters | C − B |
|---|---:|---:|---:|---:|
| ≥1 | 6 | 18 | 22 | +4 |
| ≥2 | 4 | 14 | 16 | +2 |
| ≥3 | 4 | 10 | 10 | +0 |
| ≥4 | 3 | 4 | 4 | +0 |
| ≥5 | 1 | 1 | 1 | +0 |

## 4. Simulation methodology

- Engine: `app.engine draft engine + RES-1.0 fast resolver cross-checked with app.resolution`
- Matches per dataset: 20000
- Seeds: draw `20261201`, role assignment `20261202`
- Strategy: uniform random role from remaining roles; skip the first Common draw per player when a non-Common character remains and skips are available
- Resolution: canonical RES-1.0 rules via fast in-process path; cross-checked against app.resolution.resolve_match on sampled matches
- Cross-check: A {'matches_checked': 100, 'matches_identical': 100, 'identical_pct': 100.0}, B {'matches_checked': 100, 'matches_identical': 100, 'identical_pct': 100.0}, C {'matches_checked': 100, 'matches_identical': 100, 'identical_pct': 100.0}
- Rarity weights: `{"Common": 30.0, "Uncommon": 30.0, "Rare": 22.0, "Epic": 13.0, "Legendary": 5.0}`
- Simulated strategies do not represent human behavior. No winner or approval claim is made.

## 5. Simulation results

| Metric | A | B | C |
|---|---:|---:|---:|
| Pool size | 53 | 184 | 236 |
| Matches completed | 20000 | 20000 | 20000 |
| Draft completion % | 100.0 | 100.0 | 100.0 |
| Mean team score | 693.11 | 630.38 | 618.12 |
| Team score p10 | 615 | 536 | 518 |
| Team score p50 | 691 | 631 | 618 |
| Team score p90 | 775 | 724 | 718 |
| Mean assigned healer Fit | 0.245 | 0.265 | 0.267 |
| Teams with healer Fit≥3 % | 5.35 | 5.77 | 5.59 |
| Teams with healer Fit≥4 % | 3.98 | 3.46 | 3.72 |
| Skips used | 0 | 67099 | 67135 |
| Player 1 win % | 49.91 | 49.83 | 50.3 |
| Player 2 win % | 49.88 | 49.98 | 49.61 |
| Draw % | 0.2 | 0.2 | 0.09 |
| Decided by matchup count % | 83.81 | 86.16 | 86.48 |
| Decided by combined score % | 15.98 | 13.64 | 13.43 |
| Fit 0 assignments % | 14.34 | 18.56 | 21.14 |
| Fit ≤1 assignments % | 36.33 | 42.41 | 44.13 |

### Rarity draw distribution

| Rarity | A % | B % | C % |
|---|---:|---:|---:|
| Common | 0.0 | 30.5 | 30.51 |
| Uncommon | 46.09 | 30.54 | 30.5 |
| Rare | 33.94 | 22.44 | 22.45 |
| Epic | 12.22 | 11.42 | 11.45 |
| Legendary | 7.74 | 5.1 | 5.1 |

### Average assigned role scores and matchup strength

| Role | Avg score A | Avg score B | Avg score C | Matchup draws C % | Mean abs margin C |
|---|---:|---:|---:|---:|---:|
| captain | 109.6 | 98.78 | 97.44 | 8.48 | 23.35 |
| strategist | 107.54 | 101.29 | 98.23 | 8.79 | 25.71 |
| attacker | 137.53 | 122.18 | 119.9 | 17.55 | 24.67 |
| tank | 120.25 | 104.3 | 102.31 | 13.39 | 23.52 |
| assassin | 92.47 | 82.85 | 81.05 | 8.09 | 20.7 |
| support | 96.81 | 93.25 | 91.59 | 8.03 | 22.46 |
| healer | 28.91 | 27.74 | 27.6 | 23.53 | 10.98 |

## 6. Batch 005 impact assessment

- Pool size rises from 184 to 236 (+52).
- Common roster share rises from 59 to 109 characters.
- Power 1 count rises from 11 to 47.
- Characters with no meaningful specialist role rise from 0 to 33.
- Healer Fit≥3 character count is 10 in B and 10 in C; Batch 005 adds no Fit≥3 healer.
- Mean team score changes from 630.38 in B to 618.12 in C (-12.26).
- Player 1 win rate changes from 49.83% to 50.3%.
- Fit 0 assignments rise from 18.56% to 21.14%.

Numerical differences are reported without automatic rating inflation or rarity-probability changes. The Batch 005 additions are predominantly Common-tier, low-Power utility characters; they increase pool breadth but reduce average team strength and increase weak assignments under this strategy.

## 7. Integration readiness

- Schema: `KA-IMPORT-1.0`
- Catalogue IDs imported: 62
- Importable evaluations: 52
- Held candidates preserved without ratings: 10
- No Batch 005 ID overlap with existing datasets: True
- Audited evaluation package unchanged: True
- Recommendation: Import-ready from a schema and identity perspective. Owner approval and visual/canonical artwork review are still required before production publication.

The audited package contains 7 documented rating changes and 10 Held records. No audited evaluation was modified during this cumulative analysis.

## 8. Limitations

- No verified published production snapshot was available; Datasets A-C are reconstructed draft snapshots.
- All ratings remain draft/review, not approved production data.
- Simulated role assignment is deterministic random-plus-skip and does not model human drafting.
- Visual identity verification and publication permission for artwork remain unresolved.
- Healer Fit≥3 availability is measured from ratings, not from canonical healing correctness.
- No balance changes or rarity probability changes are recommended automatically.

## 9. Validation

- Focused cumulative validation tests: 6 passed.
- Complete repository regression suite: 188 passed.
- No production publication or owner approval was performed.
