# Naruto Batch 005 — Final Evaluation Report

Batch `naruto-batch-005` · EVAL-FRAMEWORK-1.0 · NARUTO-CANON-0.1 · SCORE-1.0 · batch status `draft`. Nothing is approved or published. Fit was assigned for all 62 characters using only `fit_reference`, the Fit values were saved to a file (`naruto_batch_005_passA_fit_frozen.py`), and only then was `power_reference` opened. No Fit value was changed after Pass B.

## 1. Totals
- Candidates evaluated: **62 of 62**, in research-file order, IDs copied exactly. Completed (Draft): **62**. Held: **0**. Excluded/unresolved candidates and Enma were not evaluated.
- No record is Held, but 44 of the 62 carry low-confidence flags and need independent review (see section 11). Only 18 records are medium confidence. No record is high confidence, because primary manga was never opened.
- Evidence grades: A 18, B 32, C 12 (grades describe the quality of the demonstration as supplied; every source is inspected-secondary).

## 2. Instruction conflicts and how I resolved them
1. **Rarity and role scores.** The owner prompt asks for role scores and rarity. The attached assignment (declared authoritative) says not to calculate or insert role scores or rarity, and to keep rarity out of scope. The package contains no rarity framework or thresholds. Resolution: the import file contains **no scores or rarity**. Role scores using the formula in the prompt are in a separate **advisory** file, `naruto_batch_005_derived_role_scores_advisory.json`, which is not for import. **Rarity was not derived**, because no thresholds were supplied and I will not invent any.
2. **Held vs 62 records.** KA-IMPORT requires exactly 62 evaluations with integer Power. I did not use placeholder holds. Thin records got low Power values with explicit low-confidence flags. The owner can still convert any of them to Held.
3. **Anime-only evidence.** CANON-0.1 excludes anime-only additions by default. For 12 records the supplied evidence is mostly anime or Boruto-era, so I kept ratings at the Grade C ceiling (max 2) and flagged them. This is stricter than the evidence might deserve for Raiga Kurosuki and Hanabi Hyūga (see section 8).
4. **Stale text in the calibration file** says "100 candidates". The corrected package is 62, which I used.
5. **GitHub.** No repository or network access here, so nothing was committed or pushed to `content/naruto-batch-005`. The files are downloadable.

## 3. Power distribution
Power 1: 41 · Power 2: 19 · Power 3: 2 (Jūzō Biwa, Chiriku) · Power 4: 0 · Power 5: 0.
The skew to Power 1 is deliberate: most of these are minor or support characters, and a rank (jōnin, tokubetsu jōnin) was not accepted as evidence of ability. This is also why no character reached Power 4 or 5.

## 4. Role Fit distributions (count of characters at each level)
| Role | 0 | 1 | 2 | 3 | 4 | 5 |
|---|---|---|---|---|---|---|
| captain | 46 | 11 | 5 | 0 | 0 | 0 |
| strategist | 42 | 18 | 2 | 0 | 0 | 0 |
| attacker | 34 | 14 | 12 | 2 | 0 | 0 |
| tank | 54 | 4 | 3 | 1 | 0 | 0 |
| assassin | 49 | 11 | 2 | 0 | 0 | 0 |
| support | 13 | 39 | 9 | 1 | 0 | 0 |
| healer | 55 | 5 | 2 | 0 | 0 | 0 |
No Fit 4 or 5 was assigned. Every zero is an unevidenced zero unless the record's limitations text shows the opposite.

## 5. Role score distributions and top scorers (advisory only)
Computed from the owner-supplied formula (Fit × coefficient + Power × (20 − coefficient)); verified by script. All values fall within 0–100. Top five per role:
- Captain: Chiriku 48, Hanabi Hyūga 40, Mugino 40, Shibito Azuma 32, Ebizō 32
- Strategist: Mugino 40, Ebizō 37, Jūzō Biwa 26, Chiriku 26, Raiga Kurosuki 23
- Attacker: Jūzō Biwa 60, Chiriku 60, Raiga Kurosuki 40, Hanabi Hyūga 40, Shin 40
- Tank: Chiriku 60, Jūzō Biwa 50, Mugino 40, Might Duy 40, Raiga Kurosuki 30
- Assassin: Gōzu 40, Meizu 40, Jūzō Biwa 34, Raiga Kurosuki 27, Santa Yamanaka 27
- Support: Kussaku 54, Chiriku 43, Santa Yamanaka 40, Mugino 40, Yodo 40
- Healer: Ryōkan 37, Sekka 37, Yūgao Uzuki 23, Urushi 20, Mitate 20

## 6. Rarity
Not derived (see conflict 1). Because role scores here max out at 60, these characters would presumably land in low tiers under any framework that uses the formula above, but I have not applied one.

## 7. Specialists
- Sensors: Kussaku (Support 3, databook statement of Kirigakure's greatest sensory ability plus the Sensing Barrier), Sagan, Tsubusa, Iroha Hyūga, Nishi, Yodo (hearing) at Support 2.
- Medics: Ryōkan and Sekka (Healer 2; failed to cure Sasori's poison unaided, assisted Sakura's cure). Urushi, Mitate, Yūgao, Oyone and Kumadori are Healer 1.
- Shadow-binders: Suzaku Nara (solo hold on Naruto, Support 1) and Daen, Kasuga and Maen (joint Ten-Tails restraint, Support 1).
- Swordsmen: Jūzō Biwa, Chiriku, Zōri, Waraji. Barrier/defence: Chiriku (Tank 3). Ambush pair: Gōzu and Meizu (Assassin 2).
- Intelligence/analysis: Ebizō (Strategist 2), Mitoku, Yurika, Oyone, Kumadori at Strategist 1.

## 8. Significant calibration decisions
- **Anchors used (relative ordering only, never copied):** Zaji (P1 sensor) for non-combat sensors; Hoheto and Shikamaru/Shikaku (P2) for the Power 2 line; Torune/Choji/Neji (P3) as the line Jūzō Biwa and Chiriku sit on. Shizune (Healer 4) is far above Ryōkan/Sekka because they never treat serious cases unaided.
- **Might Duy:** the Eight Gates Released Formation is a fatal, one-time technique that killed him, so it is excluded under CANON-0.1. This leaves Power 2, flagged `DISPUTED_ECV_FATAL_TECHNIQUE`. Plausible Power 4 if the owner admits it. This is the largest rating swing in the batch.
- **Raiga Kurosuki:** evidence is anime episodes only, so Power is held at the Grade C ceiling of 2. Plausible 3–4.
- **Bunpuku:** Shukaku's sand and chakra are not attributed to the host; he never mastered the beast and no combat is shown, so Power 1.
- **Shin (Root):** reincarnation regeneration and the explosive-clay payload are excluded.
- **Jūzō Biwa:** Kubikiribōchō treated as equipment; survival of the Eight Gates formation (manga ch.668 lead) supports Tank 2.
- **One-scene characters:** a single appearance of a relevant ability gets Fit 1 (doubt rule: choose the lower, record the higher as plausible). Where two distinct techniques combined to decisive effect (Santa Yamanaka, Nonota), Fit 2.

## 9. Evidence limitations
- Every source is an inspected secondary page; primary manga, databooks and anime were not opened. 39 records have chapter/episode references checked against page text only. Page citations are leads, not primary quotations.
- 12 records rest mostly on anime or Boruto-era material (CSET: Raiga, Hanabi, Nishi, Yurui, Yūgao, Mugino, the three Senka brothers, Yodo, Furui, Bunpuku).
- Several records give no chapter reference at all (Suzaku, Daen, Kasuga, Maen, Isago, Hamaki, Azuma and others).
- Evidence summaries in the import file are drawn from the research file's capability text and not independently re-checked.

## 10. Cross-character consistency review
Checked: ceilings vs evidence grade (script-enforced, 0 violations); duplicate IDs (none); similar-evidence groups; calibration-anchor contradictions (none: anchors were not modified or copied).
- **Same evidence, same rating (kept equal):** Gōzu/Meizu; Waraji (Fit identical except Zōri's Captain 1 from anime-only leadership); Daen/Kasuga/Maen (joint restraint, P1, Support 1) vs Suzaku (solo hold, P2); the four-direction assault group on Pain (Shitō, Kokage, Saisu, Tessen: all P1, Attacker 1, rank not used as evidence); Oyone/Kumadori; Ryōkan/Sekka; Mozuku/Mawashi (Support 1); the Senka brothers (Takanami Captain 1 for leading).
- **Deliberate differences:** Tonbo (Power 2) above Mozuku/Mawashi (Power 1) because of a cited speed-and-restraint feat.
- **Strong combatants given noncombat Fit:** none. Chiriku's Captain 2 and Support 2 rest on head-monk status and barrier/seal use that protected others, not on strength.
- **Corrections made during review:** none to Fit after Pass B. Before finalising I raised Nonota and Santa Yamanaka to Support 2 on the two-technique rule above and lowered single-scene characters to 1 for consistency.
- **Possible remaining inconsistency:** jōnin-ranked characters (Gaku Inuzuka, Shinku Yūhi, Isago, Shitō, Suzaku-adjacent) sit at Power 1 while chunin-level Yodo and Gōzu are 2. This follows the evidence-over-rank rule but the owner may disagree.

## 11. Validation results
Script `naruto_batch_005_build_and_validate.py` (deterministic) reported **0 errors**: 62 records, same order and IDs as the research file; Power integers 1–5; seven lowercase Fit keys, integers 0–5; at least one evidence item for Power and each non-zero Fit; no `rarity`/`role_score`/`ecv_score`/`matchups`/`approved` keys; grade ceilings respected; all advisory role scores recomputed and within 0–100.

## 12. Remaining concerns for owner review
1. Might Duy's Eight Gates treatment (policy call).
2. Anime-only exclusion vs fairness for Raiga, Hanabi, Yūgao and the Boruto-era records.
3. Whether Boruto-era characters (Nishi, Yurui, Mugino, Senka brothers, Yodo, Hanabi) belong in this Naruto-universe batch at all.
4. 44 low-confidence records need independent verification against primary manga before approval.
5. Rarity framework and thresholds must be supplied before rarity can be derived.
6. Healer 1 for Oyone and Kumadori rests on inferred medical skill; Healer 2 for Ryōkan/Sekka and Support 3 for Kussaku rest on databook statements.
7. Several characters (Genzō, Kaiza, Kaji) are non-shinobi civilians evaluated as Power 1. The owner should confirm that civilians are eligible.
