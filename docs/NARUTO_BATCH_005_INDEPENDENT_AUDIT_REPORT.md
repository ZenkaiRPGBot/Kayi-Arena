# Naruto Batch 005 — Independent Evaluation Audit Report

## 1. Scope and status

- Batch: `naruto-batch-005`
- Corrected research package commit: `76905d2`
- Canonical policy: `NARUTO-CANON-0.1`
- Framework: `EVAL-FRAMEWORK-1.0`; scoring `SCORE-1.0`; rarity `RARITY-0.2`
- Preparation date: 2026-11-27
- Status: **draft audit preparation**. Nothing is approved, published or imported into a playable dataset.

All 62 Claude evaluations were audited individually against the corrected research package, the calibration reference, the approved Power/Fit definitions, evidence ceilings and canonical-exclusion rules. Original Claude outputs were preserved byte-for-byte.

Original-output SHA-256 values:

- `naruto_batch_005_claude_evaluation.json`: `891a11aef394826d5cdf072e37c2709881d06116119c3d077bc50472f6dbc5c3`
- `naruto_batch_005_evaluation_details.json`: `3242dcef7e5c6126252d3f112cd1e5277d9ca410e97d50b2101aa55fb9ee305b`
- `naruto_batch_005_final_report.md`: `f2adaf2f9b73fadd2ab7c57500c3daab9f26d11222236b3cb33ab741a7aa1a8a`
- `naruto_batch_005_derived_role_scores_advisory.json`: `3d54cf17a9ee0ced4f378d11a197feccc2827154b7b1bf50e066824f9e1dca1c`
- `naruto_batch_005_build_and_validate.py`: `fab4b2cacccedb3bbc457226dc9103059d38c7ec2b26573197d1a9e969526ae2`
- `naruto_batch_005_passA_fit_frozen.py`: `d65b4e53ac4a6670fbd93997a03308f0718534534cf9a847b7110e075a305f7e`

## 2. Outcome summary

- Candidates accounted for: **62**
- Importable audited evaluations: **52**
- Held and excluded from import: **10**
- Rating changes: **7** across 4 records
- No Power or Role Fit was invented to satisfy an import schema.
- No Fit 4 or Fit 5 was introduced; the supplied evidence does not support a specialist ceiling upgrade.

### Power distribution

| Power | Claude original | Audited importable |
|---:|---:|---:|
| 1 | 41 | 36 |
| 2 | 19 | 14 |
| 3 | 2 | 2 |
| 4 | 0 | 0 |
| 5 | 0 | 0 |

The reduction in Power 1 and Power 2 counts reflects 10 held records and one justified Power correction, not a forced distribution.

### Role Fit distribution (audited importable)

| Role | 0 | 1 | 2 | 3 | 4 | 5 |
|---|---:|---:|---:|---:|---:|---:|
| captain | 40 | 9 | 3 | 0 | 0 | 0 |
| strategist | 38 | 13 | 1 | 0 | 0 | 0 |
| attacker | 33 | 10 | 7 | 2 | 0 | 0 |
| tank | 46 | 3 | 2 | 1 | 0 | 0 |
| assassin | 41 | 9 | 2 | 0 | 0 | 0 |
| support | 12 | 33 | 6 | 1 | 0 | 0 |
| healer | 48 | 2 | 2 | 0 | 0 | 0 |

No Fit 4 or Fit 5 remains justified. The strongest available specialist level in this batch is Fit 3, with evidence limited to inspected secondary profiles and no primary manga inspection.

### Rarity distribution (authoritative RARITY-0.2 with Naruto healer floors)

| Rarity | Count |
|---|---:|
| Common | 50 |
| Uncommon | 2 |
| Rare | 0 |
| Epic | 0 |
| Legendary | 0 |

The skew to Common reflects genuinely low Power/Fit evidence, not a rarity manipulation.

## 3. Held candidates

| ID | Name | Hold code | Reason |
|---|---|---|---|
| dattebayo:901 | Nishi (sensor) | BORUTO_ERA_ELIGIBILITY_UNRESOLVED | Boruto-era sensor with no verified Naruto-era version in the supplied package. The authoritative Naruto universe policy does not independently expand to Boruto-exclusive characters; owner decision required. |
| dattebayo:435 | Hanabi Hyūga | BORUTO_ERA_ELIGIBILITY_UNRESOLVED | Hanabi's supplied combat evidence is adaptation/Boruto-era material; no verified Naruto-era combat baseline. Hold rather than silently expanding the Naruto universe boundary. |
| dattebayo:1413 | Yurui | BORUTO_ERA_ELIGIBILITY_UNRESOLVED | Boruto-era anime evidence with no verified Naruto-era ability baseline; hold for owner review. |
| dattebayo:846 | Mugino | BORUTO_ERA_ELIGIBILITY_UNRESOLVED | Boruto-era candidate with adaptation-sensitive evidence and disputed era eligibility. |
| dattebayo:1068 | Makinami Senka | BORUTO_ERA_ELIGIBILITY_UNRESOLVED | Boruto-era Senka brother; era eligibility unresolved under NARUTO-CANON-0.1. |
| dattebayo:1069 | Sazanami Senka | BORUTO_ERA_ELIGIBILITY_UNRESOLVED | Boruto-era Senka brother; era eligibility unresolved under NARUTO-CANON-0.1. |
| dattebayo:1070 | Takanami Senka | BORUTO_ERA_ELIGIBILITY_UNRESOLVED | Boruto-era Senka brother; era eligibility unresolved under NARUTO-CANON-0.1. |
| dattebayo:1377 | Yodo | BORUTO_ERA_ELIGIBILITY_UNRESOLVED | Boruto-era hearing/support specialist; era eligibility unresolved under NARUTO-CANON-0.1. |
| dattebayo:801 | Hamaki Mimura | BORROWED_EQUIPMENT_ONLY | The only demonstrated action uses Minato's Flying Thunder God kunai; sword skill is merely implied and no personal technique or result is supplied. Borrowed equipment is excluded under NARUTO-CANON-0.1. |
| dattebayo:434 | Hyūga Elder | INSUFFICIENT_DEMONSTRATED_ABILITY | Only anime-only, implied taijutsu and a long leap are supplied; the source explicitly says the extent of his abilities is unknown. No defensible numerical evaluation can be established. |

Boruto-era candidates were held rather than independently expanding the Naruto universe boundary. `Hyūga Elder` and `Hamaki Mimura` were held because their only supplied capabilities were an implied anime-only demonstration and borrowed equipment respectively.

## 4. Rating changes

| ID | Name | Field | Change | Reason | Calibration | Confidence |
|---|---|---|---|---|---|---|
| dattebayo:1337 | Yūgao Uzuki | power | 2 → 1 | Power 2 was the adaptation ceiling, not demonstrated combat capability. | Zaji (Power 1 support specialist) and non-combatant anchors support Power 1 for a support-only character with no demonstrated combat effectiveness. | low |
| dattebayo:1337 | Yūgao Uzuki | attacker | 2 → 0 | Anime-only kenjutsu expansion cannot support Attacker Fit under the policy. | Attacker Fit requires direct offensive effectiveness; comparison with Hinata and Ino anchors keeps zero where offense is not demonstrated. | low |
| dattebayo:1337 | Yūgao Uzuki | assassin | 1 → 0 | Remove unsupported Assassin Fit. | Kakashi and Torune anchors require concrete stealth or infiltration actions. | low |
| dattebayo:1337 | Yūgao Uzuki | strategist | 1 → 0 | Remove unsupported Strategist Fit. | Shikamaru/Shikaku anchors require demonstrated tactical action. | low |
| dattebayo:810 | Mitate | healer | 1 → 0 | Apply the canonical policy to anime-only healing evidence. | Healer Fit requires demonstrated treatment of others, not diagnosis alone; Shizune and Sakura are treatment anchors. | medium |
| dattebayo:948 | Oyone | healer | 1 → 0 | An inferred medical role is not a demonstrated ability to treat others. | Karin (Healer 3) and Shizune (Healer 4) are treatment anchors; analysis alone does not meet Healer 1. | low |
| dattebayo:706 | Kumadori | healer | 1 → 0 | Remove an inferred Healer Fit that lacks a demonstrated treatment action. | Karin (Healer 3) and Shizune (Healer 4) require actual healing actions; inference-only medical knowledge does not qualify. | low |

All other ratings were retained. Might Duy remains Power 2 because the fatal, non-repeatable Eighth Gate is correctly excluded; no sustainable substitute feat supports a higher rating. Raiga Kurosuki remains at the Grade C anime-only ceiling rather than being upgraded without manga evidence.

## 5. Scores and advisory comparison

- Advisory file matches original Claude ratings for all 62 records.
- Advisory file matches audited ratings for 58 records.
- The four differences correspond to the four records with changed ratings; derived scores were recomputed with the authoritative `SCORE-1.0` engine, not the advisory copy.
- No rarity is stored in the KA-IMPORT evaluation records; authoritative rarity is reported in the audit-details companion.

## 6. Strongest role specialists in the importable pool

- **captain**: Chiriku (48), Shibito Azuma (32), Ebizō (32), Raiga Kurosuki (28), Might Duy (28)
- **strategist**: Ebizō (37), Jūzō Biwa (26), Chiriku (26), Raiga Kurosuki (23), Santa Yamanaka (23)
- **attacker**: Jūzō Biwa (60), Chiriku (60), Raiga Kurosuki (40), Shin (40), Gōzu (40)
- **tank**: Chiriku (60), Jūzō Biwa (50), Might Duy (40), Raiga Kurosuki (30), Bunpuku (20)
- **assassin**: Gōzu (40), Meizu (40), Jūzō Biwa (34), Raiga Kurosuki (27), Santa Yamanaka (27)
- **support**: Kussaku (54), Chiriku (43), Santa Yamanaka (40), Nonota (40), Iroha Hyūga (37)
- **healer**: Ryōkan (37), Sekka (37), Urushi (20), Yūgao Uzuki (20), Jūzō Biwa (9)

Healer coverage: no importable record has Healer Fit 3 or higher. The highest audited Healer Fit is 2 (Ryōkan, Sekka), both conditional on assistance. The 1,000-match simulation therefore observed 0% of teams with Healer Fit ≥3.

## 7. Artwork review

- Catalogue candidates: 62
- Technically valid manifest images: 63
- Importable candidates with technically valid artwork: 52/52
- Visual identity verification: not performed.
- Canonical-version accuracy of images: not visually verified.
- Publication permission: source-dependent; review required before any publication.

A successful download is not treated as publication-safe or as proof of correct identity/canonical version.

## 8. Simulation

- Engine: `app.engine deterministic draft engine`
- Matches requested/completed: 1000/1000
- Seed: 20261127; role selection: uniform random from remaining roles with Python random.Random(seed)
- Rarity weights: `{"Common": 30.0, "Uncommon": 30.0, "Rare": 22.0, "Epic": 13.0, "Legendary": 5.0}`
- Pool size: 52
- Rarity draw distribution: `{"Common": 85.71, "Uncommon": 14.29, "Rare": 0.0, "Epic": 0.0, "Legendary": 0.0}`
- Average role scores: `{"assassin": 14.3, "attacker": 22.98, "captain": 17.0, "healer": 6.34, "strategist": 10.83, "support": 21.57, "tank": 19.87}`
- Team-score advantage: `{"player_1_higher_score_pct": 48.9, "note": "Draft-order comparison of summed SCORE-1.0 role scores, not canonical match resolution."}`
- No canonical match winner is claimed; this is a draft-engine and SCORE-1.0 team-shape check only.

## 9. Identity and duplicate checks

- No duplicate character IDs within the Claude package, the audited package or the import package.
- Claude's evaluation order exactly matches the corrected research-package order.
- Overlap with previously evaluated Naruto datasets:
  - `naruto_evaluated_60_dataset.json`: 0 overlapping IDs
  - `naruto_expansion_003_004_evaluated_dataset.json`: 0 overlapping IDs
  - `naruto_batch_003_evaluated_dataset.json`: 0 overlapping IDs
- Enma remains a manual identity-mapping item and was not evaluated.

## 10. Validation

- Offline audit validator: passed (62 accounted, 52 importable, 10 held, 7 documented changes).
- Focused audit tests: 15 passed.
- Full repository regression suite: 182 passed after the audit files were generated.
- Structural checks: KA-IMPORT format, exact role keys, integer ranges, evidence presence, no forbidden rating keys.
- Numerical checks: authoritative score and rarity recomputation for all 62 records.

## 11. Complete before-and-after comparison

Fit order: Captain/Strategist/Attacker/Tank/Assassin/Support/Healer.

| ID | Name | Power before | Power after | Fit before | Fit after | Status | Changed | Decision |
|---|---|---:|---:|---|---|---|---|---|
| dattebayo:879 | Suzaku Nara | 2 | 2 | 0/0/0/0/0/1/0 | 0/0/0/0/0/1/0 | importable | no | All Claude ratings retained after independent review. |
| dattebayo:441 | Iroha Hyūga | 1 | 1 | 0/0/0/0/0/2/0 | 0/0/0/0/0/2/0 | importable | no | All Claude ratings retained after independent review. |
| dattebayo:724 | Raiga Kurosuki | 2 | 2 | 1/1/2/1/1/1/0 | 1/1/2/1/1/1/0 | importable | no | All Claude ratings retained after independent review. |
| dattebayo:1370 | Santa Yamanaka | 2 | 2 | 0/1/0/0/1/2/0 | 0/1/0/0/1/2/0 | importable | no | All Claude ratings retained after independent review. |
| dattebayo:901 | Nishi (sensor) | 1 | Held | 0/0/0/0/0/2/0 | Held | held | no | Excluded from importable evaluation package pending owner review. |
| dattebayo:46 | Shitō Akimichi | 1 | 1 | 0/0/1/0/0/1/0 | 0/0/1/0/0/1/0 | importable | no | All Claude ratings retained after independent review. |
| dattebayo:435 | Hanabi Hyūga | 2 | Held | 2/1/2/0/0/1/0 | Held | held | no | Excluded from importable evaluation package pending owner review. |
| dattebayo:841 | Mozuku | 1 | 1 | 0/0/0/0/0/1/0 | 0/0/0/0/0/1/0 | importable | no | All Claude ratings retained after independent review. |
| dattebayo:871 | Daen Nara | 1 | 1 | 0/0/0/0/0/1/0 | 0/0/0/0/0/1/0 | importable | no | All Claude ratings retained after independent review. |
| dattebayo:874 | Kasuga Nara | 1 | 1 | 0/0/0/0/0/1/0 | 0/0/0/0/0/1/0 | importable | no | All Claude ratings retained after independent review. |
| dattebayo:875 | Maen Nara | 1 | 1 | 0/0/0/0/0/1/0 | 0/0/0/0/0/1/0 | importable | no | All Claude ratings retained after independent review. |
| dattebayo:1094 | Shin | 2 | 2 | 0/0/2/0/1/0/0 | 0/0/2/0/1/0/0 | importable | no | All Claude ratings retained after independent review. |
| dattebayo:1413 | Yurui | 2 | Held | 0/1/2/0/0/1/0 | Held | held | no | Excluded from importable evaluation package pending owner review. |
| dattebayo:464 | Gaku Inuzuka | 1 | 1 | 0/0/1/0/0/1/0 | 0/0/1/0/0/1/0 | importable | no | All Claude ratings retained after independent review. |
| dattebayo:1332 | Urushi | 1 | 1 | 0/0/0/0/0/1/1 | 0/0/0/0/0/1/1 | importable | no | All Claude ratings retained after independent review. |
| dattebayo:1337 | Yūgao Uzuki | 2 | 1 | 0/1/2/0/1/1/1 | 0/0/0/0/0/1/1 | importable | yes | Power and three unsupported role Fits lowered; Support 1 and Healer 1 retained. |
| dattebayo:122 | Jūzō Biwa | 3 | 3 | 0/1/3/2/1/1/0 | 0/1/3/2/1/1/0 | importable | no | All Claude ratings retained after independent review. |
| dattebayo:338 | Gōzu | 2 | 2 | 0/1/2/0/2/1/0 | 0/1/2/0/2/1/0 | importable | no | All Claude ratings retained after independent review. |
| dattebayo:779 | Meizu | 2 | 2 | 0/1/2/0/2/1/0 | 0/1/2/0/2/1/0 | importable | no | All Claude ratings retained after independent review. |
| dattebayo:846 | Mugino | 2 | Held | 2/2/2/2/1/2/0 | Held | held | no | Excluded from importable evaluation package pending owner review. |
| dattebayo:1374 | Kokage Yanagikage | 1 | 1 | 0/0/1/0/0/0/0 | 0/0/1/0/0/0/0 | importable | no | All Claude ratings retained after independent review. |
| dattebayo:210 | Might Duy | 2 | 2 | 1/0/2/2/0/1/0 | 1/0/2/2/0/1/0 | importable | no | All Claude ratings retained after independent review. |
| dattebayo:1068 | Makinami Senka | 1 | Held | 0/0/1/0/0/1/0 | Held | held | no | Excluded from importable evaluation package pending owner review. |
| dattebayo:1069 | Sazanami Senka | 1 | Held | 0/0/1/0/0/1/0 | Held | held | no | Excluded from importable evaluation package pending owner review. |
| dattebayo:1070 | Takanami Senka | 1 | Held | 1/0/1/0/0/1/0 | Held | held | no | Excluded from importable evaluation package pending owner review. |
| dattebayo:1232 | Tonbo Tobitake | 2 | 2 | 0/1/1/0/0/1/0 | 0/1/1/0/0/1/0 | importable | no | All Claude ratings retained after independent review. |
| dattebayo:1377 | Yodo | 2 | Held | 0/1/2/1/0/2/0 | Held | held | no | Excluded from importable evaluation package pending owner review. |
| dattebayo:103 | Shibito Azuma | 1 | 1 | 2/1/0/0/0/0/0 | 2/1/0/0/0/0/0 | importable | no | All Claude ratings retained after independent review. |
| dattebayo:213 | Ebizō | 1 | 1 | 2/2/0/0/0/1/0 | 2/2/0/0/0/1/0 | importable | no | All Claude ratings retained after independent review. |
| dattebayo:251 | Furui | 2 | 2 | 1/0/0/0/0/1/0 | 1/0/0/0/0/1/0 | importable | no | All Claude ratings retained after independent review. |
| dattebayo:473 | Isago | 1 | 1 | 1/0/0/0/0/1/0 | 1/0/0/0/0/1/0 | importable | no | All Claude ratings retained after independent review. |
| dattebayo:563 | Saisu Kamano | 1 | 1 | 0/0/1/0/0/0/0 | 0/0/1/0/0/0/0 | importable | no | All Claude ratings retained after independent review. |
| dattebayo:787 | Shinobu Mibu | 1 | 1 | 1/0/0/0/1/1/0 | 1/0/0/0/1/1/0 | importable | no | All Claude ratings retained after independent review. |
| dattebayo:801 | Hamaki Mimura | 1 | Held | 0/0/0/0/0/1/0 | Held | held | no | Excluded from importable evaluation package pending owner review. |
| dattebayo:820 | Mizunoto | 2 | 2 | 0/0/0/0/1/0/0 | 0/0/0/0/1/0/0 | importable | no | All Claude ratings retained after independent review. |
| dattebayo:905 | Nonota | 2 | 2 | 0/0/1/0/0/2/0 | 0/0/1/0/0/2/0 | importable | no | All Claude ratings retained after independent review. |
| dattebayo:1428 | Zōri | 2 | 2 | 1/0/2/0/1/0/0 | 1/0/2/0/1/0/0 | importable | no | All Claude ratings retained after independent review. |
| dattebayo:146 | Chiriku | 3 | 3 | 2/1/3/3/0/2/0 | 2/1/3/3/0/2/0 | importable | no | All Claude ratings retained after independent review. |
| dattebayo:1350 | Waraji | 2 | 2 | 0/0/2/0/1/0/0 | 0/0/2/0/1/0/0 | importable | no | All Claude ratings retained after independent review. |
| dattebayo:131 | Bunpuku | 1 | 1 | 0/0/0/1/0/1/0 | 0/0/0/1/0/1/0 | importable | no | All Claude ratings retained after independent review. |
| dattebayo:1000 | Sabu | 2 | 2 | 0/1/1/0/0/1/0 | 0/1/1/0/0/1/0 | importable | no | All Claude ratings retained after independent review. |
| dattebayo:810 | Mitate | 1 | 1 | 0/0/0/0/0/1/1 | 0/0/0/0/0/1/0 | importable | yes | Healer Fit removed after anime-only exclusion. |
| dattebayo:1005 | Sagan | 1 | 1 | 0/0/0/0/0/2/0 | 0/0/0/0/0/2/0 | importable | no | All Claude ratings retained after independent review. |
| dattebayo:1319 | Ugatsu | 1 | 1 | 0/0/0/0/1/0/0 | 0/0/0/0/1/0/0 | importable | no | All Claude ratings retained after independent review. |
| dattebayo:812 | Mitoku | 1 | 1 | 1/1/0/0/0/1/0 | 1/1/0/0/0/1/0 | importable | no | All Claude ratings retained after independent review. |
| dattebayo:434 | Hyūga Elder | 1 | Held | 1/1/1/0/0/0/0 | Held | held | no | Excluded from importable evaluation package pending owner review. |
| dattebayo:544 | Kaiza | 1 | 1 | 0/0/0/1/0/1/0 | 0/0/0/1/0/1/0 | importable | no | All Claude ratings retained after independent review. |
| dattebayo:1236 | Tessen Togeito | 1 | 1 | 0/0/1/0/0/0/0 | 0/0/1/0/0/0/0 | importable | no | All Claude ratings retained after independent review. |
| dattebayo:545 | Kaji | 1 | 1 | 0/0/0/0/0/1/0 | 0/0/0/0/0/1/0 | importable | no | All Claude ratings retained after independent review. |
| dattebayo:1389 | Yoshiteru | 1 | 1 | 1/0/1/0/0/0/0 | 1/0/1/0/0/0/0 | importable | no | All Claude ratings retained after independent review. |
| dattebayo:203 | Mawashi Dokuraku | 1 | 1 | 0/0/0/0/0/1/0 | 0/0/0/0/0/1/0 | importable | no | All Claude ratings retained after independent review. |
| dattebayo:1264 | Tsubusa | 1 | 1 | 0/0/0/0/0/2/0 | 0/0/0/0/0/2/0 | importable | no | All Claude ratings retained after independent review. |
| dattebayo:305 | Genzō | 1 | 1 | 0/0/0/0/0/0/0 | 0/0/0/0/0/0/0 | importable | no | All Claude ratings retained after independent review. |
| dattebayo:1398 | Shinku Yūhi | 1 | 1 | 1/0/0/0/0/1/0 | 1/0/0/0/0/1/0 | importable | no | All Claude ratings retained after independent review. |
| dattebayo:1176 | Tajiki | 1 | 1 | 0/0/1/0/0/0/0 | 0/0/1/0/0/0/0 | importable | no | All Claude ratings retained after independent review. |
| dattebayo:729 | Kussaku | 1 | 1 | 0/0/0/0/0/3/0 | 0/0/0/0/0/3/0 | importable | no | All Claude ratings retained after independent review. |
| dattebayo:882 | Natori | 1 | 1 | 0/0/0/0/0/1/0 | 0/0/0/0/0/1/0 | importable | no | All Claude ratings retained after independent review. |
| dattebayo:948 | Oyone | 1 | 1 | 0/1/0/0/0/1/1 | 0/1/0/0/0/1/0 | importable | yes | Healer Fit removed; all other ratings retained. |
| dattebayo:706 | Kumadori | 1 | 1 | 0/1/0/0/0/1/1 | 0/1/0/0/0/1/0 | importable | yes | Healer Fit removed; all other ratings retained. |
| dattebayo:1410 | Yurika | 1 | 1 | 0/1/0/0/0/1/0 | 0/1/0/0/0/1/0 | importable | no | All Claude ratings retained after independent review. |
| dattebayo:987 | Ryōkan | 1 | 1 | 0/0/0/0/0/1/2 | 0/0/0/0/0/1/2 | importable | no | All Claude ratings retained after independent review. |
| dattebayo:1057 | Sekka | 1 | 1 | 0/0/0/0/0/1/2 | 0/0/0/0/0/1/2 | importable | no | All Claude ratings retained after independent review. |

## 12. Publication safeguard

This package is prepared for owner review only. No character is approved, published, scored into a production dataset or activated in gameplay. Rarity values are advisory audit outputs derived from the authoritative implementation, not production assignments.
