# Naruto Expansion 003–004 — Consolidated Content Preparation Report

**Prepared:** 2026-11-27
**Branch:** `content/naruto-batch-003`
**Status:** Draft review only — **nothing is approved, published, or auto-imported.**
**Frameworks:** `EVAL-FRAMEWORK-1.0` · `NARUTO-CANON-0.1` · `SCORE-1.0` · `RARITY-0.2`

## 1. Scope and inputs

| Input | Records | Draft | Held |
|---|---:|---:|---:|
| Batch 003 — Claude original | 50 | 47 | 3 |
| Batch 003 — revised (authoritative) | 50 | 49 | 1 |
| Batch 004-A | 49 | 32 | 17 |
| Batch 004-B | 50 | 26 | 24 |
| **Consolidated total** | **149** | **132** | **17** |

- Claude's original evaluation files are preserved byte-for-byte. The combined file
  `data/naruto_expansion_003_004_evaluations.json` embeds each record's `original`
  entry, the `revised` entry, and a per-field `changes[]` list.
- Batch 003 integration uses `data/naruto_batch_003_evaluations_revised.json`, not the
  original file.
- Every rating change is recorded in `data/naruto_expansion_003_004_change_log.json`
  (219 change entries, including the 8 batch-003 corrections).

## 2. Identity resolution

- Catalogue identities resolved: **148 / 149**.
- Duplicate playable identities introduced: **0**. No expansion character collides with
  the original 60-character roster.
- Sakon and Ukon remain **one combined playable record**; both source identities are
  preserved in the record and mapping notes.
- Named summons/ninken with a distinct identity and demonstrated abilities are eligible
  (Gamakichi, Gamaken, Gamahiro, Katsuyu, Manda, Aoda, Kamatari, Pakkun, etc.).
- `Enma` is **unmatched**: the documented abilities exist, but there is no Dattebayo
  catalogue/API entry. It is excluded from the playable dataset rather than fabricated.

Resolved aliases (evaluation name → catalogue identity):

`C (Kumogakure shinobi)` → `C`; `Reto — First Kazekage` → `Reto`;
`Shamon — Second Kazekage` → `Shamon`; `Byakuren — First Mizukage` → `Byakuren`;
`Ishikawa — First Tsuchikage` → `Ishikawa`; `A — First Raikage` → `A (First Raikage)`;
`A — Second Raikage` → `A (Second Raikage)`; `Kiri — Allied Shinobi Forces` → `Kiri (ninja)`;
`Hoheto Hyuga` → `Hoheto Hyūga`; `Yoroi Akado` → `Yoroi Akadō`; `Chukichi` → `Chūkichi`;
`Kakko` → `Kakkō`; `Choji Akimichi` → `Chōji Akimichi`; `Chojuro` → `Chōjūrō`;
`Nono Yakushi` → `Nonō Yakushi`.

Identity notes:
- `C` resolves to the Kumogakure shinobi (`dattebayo:135`), not a generic name match.
- `Kiri` resolves to the Kirigakure medical-nin, not the Boruto-era villager.
- `Zaji` resolves to the Fourth War Konoha sensor, not the gambler.
- `Reto`, `Shamon`, `Byakuren`, `Ishikawa`, and both `A` records are Kage identities,
  matched to their disambiguated catalogue entries.

## 3. Evaluation revisions

37 records were revised by targeted research: 15 in 004-A, 16 in 004-B, and 6 in
batch 003 (Choji, Shizune, Dan Kato, Jūgo, Mabui, Yugito). 27 records changed evaluation status: 25 Held → Draft conversions plus the
two batch-003 conversions (Dan Kato, Mabui).

### 3.1 Held → Draft conversions

- **004-A (11):** Yoroi Akadō, Misumi Tsurugi, Kō Hyūga, Iwashi Tatami, Biwako Sarutobi,
  Taji, Tekka Uchiha, Inabi Uchiha, Yashiro Uchiha, Kagami Uchiha, Torifu Akimichi.
- **004-B (14):** Chūkichi, Gari, Toroi, Dodai, Motoi, Kakkō, Taiseki, Mahiru, Urakaku,
  Yūra, Matsuri, Maki, Shamon, Kamatari.

Each conversion carries documented abilities, an explicit canonical version, a
confidence level, and at least one evidence lead. None is marked approved.

### 3.2 Rating corrections

| Character | Change | Rationale |
|---|---|---|
| Torune Aburame | Power 4 → 3 | Contact-kill specialist; high-jōnin tier, not Kage-level. Attacker/Assassin 4 retained. |
| Nonō Yakushi | Captain 2 → 3 | Documented captain of the Konoha Medic Corps. Healer 3 retained. |
| Mito Uzumaki | Support 3 → 4 | Sealed the entirety of Kurama; top-tier fūinjutsu. Power remains 2 (no combat showings). |
| Ibiki Morino | Strategist 4 retained | Explicitly interpreted as interrogation/intelligence planning, not battlefield command. |
| Mifune | Power 4 retained | Iaijutsu that disrupts hand seals; Kage Summit-level performance. |
| Kinkaku | Power 4 retained | Version 2 cloak demonstrated on-panel; Treasured Tools treated as equipment. |
| Ginkaku | Power 3 retained | Cloak documented but not demonstrated on-panel; one tier below Kinkaku. |
| Blue B | Power 4 retained | Cloak and chakra arms demonstrated; reanimation benefits excluded. |

Batch-003 corrections carried into the combined file: Dan Kato Held → Draft (Ghost
Transformation); Mabui Held → Draft and Support 2 → 3 (Heavenly Transfer); Shizune
Captain 2 → 3 and Healer 3 → 4 (Medical Division captain); Jūgo Healer 0 → 2 (Cellular
Regeneration Ejection); Yugito Nii evidence corrected to capture by Hidan and Kakuzu;
Chōji canonical version confirmed (Butterfly Mode without pills).

### 3.3 Records intentionally left Held

| Batch | Character | Reason |
|---|---|---|
| 003 | White Zetsu | Clone identity ambiguity; mindless-clone eligibility unresolved. Ratings retained as reference only. |
| 004-A | Tajima Uchiha, Butsuma Senju, Itama Senju, Kawarama Senju, Ashina Uzumaki, Nawaki | Insufficient demonstrated feats. |
| 004-B | Baiu, Midare, Mubi, Kagari, Karura, Reto, Byakuren, A (First Raikage), A (Second Raikage), Ishikawa | Insufficient or unverifiable combat evidence. |

Held records never receive a rarity or importable rating. Where a Held record has
legacy ratings, they are labelled `*_reference` and cannot enter the playable pool.

## 4. Artwork

- Characters with at least one valid image: **148 / 148**.
- Images validated: **181 total**, **180 valid**, **0 duplicate hashes**.
- One non-blocking secondary failure: Gamakichi's `Gamakichi.png` returns HTTP 404;
  his primary image is valid, so coverage is complete.
- Source accessibility is tracked separately from identity correctness:
  `source_accessible` means the file downloaded and decoded, while `identity_check`
  records whether the source record was matched by name/alias, resolved from an alias,
  combined (Sakon/Ukon), or is still uncertain.
- Identity breakdown: 143 source-name matches, 3 resolved aliases, 1 combined record,
  1 uncertain (White Zetsu). Visual identity was **not** independently verified for any
  image; the check is a source-record match plus documented ambiguity flags.
- Ten dead lowercase `.png` URLs were corrected to uppercase `.PNG`; the validated
  catalogue preserves those URLs.
- Source accessibility is tracked separately from identity correctness. Uncertain
  images and duplicate-hash groups are flagged in the image report.
- Artwork binaries live in `data/naruto_images/` (gitignored) and are **not** committed.

## 5. Scoring and rarity (SCORE-1.0 / RARITY-0.2)

Playable Draft records: **131**. Held records: **17**.

| Rarity | Count |
|---|---:|
| Common | 59 |
| Uncommon | 64 |
| Rare | 7 |
| Epic | 1 |
| Legendary | 0 |

| Power | Count |
|---|---:|
| 1 | 11 |
| 2 | 50 |
| 3 | 64 |
| 4 | 6 |
| 5 | 0 |

Per-batch rarity (Draft only):

| Batch | Common | Uncommon | Rare | Epic |
|---|---:|---:|---:|---:|
| 003 | 12 | 32 | 4 | 1 |
| 004-A | 31 | 12 | 0 | 0 |
| 004-B | 16 | 20 | 3 | 0 |

The Naruto healer floor (`healer_fit_4_min_rare`) is applied: Shizune is promoted to
Rare. Rarity is computed only for complete Draft records; no Held record receives a
published rarity.

## 6. Balance simulation

Both scenarios use the real engine (`app.engine` `start_draft` / `shuffle` /
`assign_role`) with a seeded draw source. Each turn the active player shuffles and
assigns a uniformly random remaining role. Team strength is the sum of SCORE-1.0 role
scores.

| Scenario | Drafts | Failures | Avg actions | P1 win rate (all) | P1 win rate (decisive) | P1 advantage |
|---|---:|---:|---:|---:|---:|---:|
| Expansion only (131) | 10,000 | 0 | 28.0 | 49.74% | 50.06% | +0.06 pp |
| Combined roster (184) | 10,000 | 0 | 28.0 | 48.90% | 49.19% | −0.81 pp |

- Average team scores: expansion 269.61 (P1) / 269.68 (P2); combined 289.78 / 291.63.
- Ties: 63 expansion, 58 combined.
- Healer-fit-4+ pool: expansion Shizune only; combined Tsunade, Sakura Haruno, Katsuyu,
  Shizune.
- Healer-specialist picks: 4,946 (expansion) and 3,987 (combined). The previous
  `healer_high_fit_picks: 0` bug is fixed.
- No failure reasons were recorded in either scenario.

Interpretation: neither pool shows a first-player advantage beyond noise at 10,000
drafts. The combined roster is slightly P2-favoured but within normal simulation
variance; no rating change is warranted from this run.

## 7. Deliverables

| File | Contents |
|---|---|
| `data/naruto_expansion_003_004_evaluations.json` | 149 records with original + revised provenance and per-record changes |
| `data/naruto_expansion_003_004_change_log.json` | 219 field-level changes |
| `data/naruto_expansion_003_004_catalogue.json` | 148 matched candidates with validated images |
| `data/naruto_expansion_003_004_image_manifest.json` | 181 image records, 180 valid |
| `data/naruto_expansion_003_004_image_report.json` | Image validation detail |
| `data/naruto_expansion_003_004_evaluated_dataset.json` | 131 Draft + 17 Held integrated records |
| `data/naruto_expansion_003_004_ka_import.json` | KA-IMPORT-1.0, 131 importable Draft + 17 non-importable Held |
| `data/naruto_expansion_003_004_integration_report.json` | Counts, distributions, duplicate profiles, issues |
| `data/naruto_expansion_003_004_balance_report.json` | 20,000 total simulated drafts |
| `data/naruto_expansion_003_004_review_gallery.html` | Self-contained review gallery with filters |

Gallery features: text search across names, aliases, canonical versions, evidence and
flags; filters for batch, rarity, status, confidence, missing artwork, disputed/flagged
records, and revised records; embedded thumbnails; per-record evidence, role fits,
role scores, rarity detail, and previous→revised change tables.

## 8. Validation and regression

- Expansion-specific tests: `tests/test_naruto_expansion_003_004.py` covers provenance,
  counts, Held null-safety, KA-IMPORT separation, image coverage, 10,000-draft runs,
  change-log conversions, and the no-publication guarantee.
- Full regression suite: `.\.venv\Scripts\python.exe -m pytest tests -q` →
  **160 passed** (6m11s), including the 9 expansion-specific tests. No regressions.
- Content changes are isolated from Antigravity's UI/database/gameplay work; this
  branch only touches `data/`, `docs/`, `scripts/`, and tests.

## 9. Limitations and owner actions

1. **Enma** remains unmatched and excluded. A source identity from the owner is
   required before it can be evaluated.
2. Gamakichi has one missing secondary image; primary artwork is valid.
3. Most evidence leads are search-summary or secondary-source level. Primary-manga
   verification is still flagged on 78 records (uppercase and lowercase flag variants
   combined). Confidence split: 100 low, 48 medium, 0 high.
4. 25 Held→Draft conversions rely on secondary sources; owner review should prioritise
   these records.
5. Live Telegram/Render verification still needs owner-provided logs or dashboard
   access.
6. **No character is approved or published.** Owner review and explicit approval are
   required before any import or release.

## 10. Recommended review order

1. The 25 Held→Draft conversions (section 3.1).
2. The targeted rating decisions (section 3.2).
3. The 17 intentionally Held records (section 3.3).
4. Image-rights review before publication.
5. Balance review of the six Power-4 Draft records: Rasa, Kimimaro, Darui (batch 003)
   and Kinkaku, Blue B, Mifune (batch 004-B).
