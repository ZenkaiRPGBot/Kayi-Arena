# Naruto Batch 005 — Stage 01 research report

**Date:** 2026-11-27  
**Branch:** `content/naruto-batch-005`  
**Frameworks:** `EVAL-FRAMEWORK-1.0` · `NARUTO-CANON-0.1` · `SCORE-1.0` (boundary reference) · `RARITY-0.2` (out of scope)  
**Status:** Stage 01 research and artwork preparation only. No Power, Role Fit, rarity, score, approval or publication has been assigned.

## 1. Scope and outcome

Batch 005 adds **100 distinct eligible Naruto candidates** without modifying the original catalogue or Batches 003–004. The package is intentionally self-contained for one Claude conversation: it embeds the framework, canon policy, evidence rules, calibration, exact output contract and a ready-to-use assignment prompt.

| Deliverable | Status |
|---|---|
| `data/naruto_batch_005_selected_names.json` | Frozen 100-name selection input for reproduction. |
| `data/naruto_batch_005_catalogue.json` | 100 candidates, 0 unmatched |
| `data/naruto_batch_005_research.json` | 100 research records, no ratings |
| `data/naruto_batch_005_image_manifest.json` | 104 per-image records, full candidate coverage |
| `data/naruto_batch_005_calibration.json` | 20 reviewed-draft anchors; fit/power sections separated |
| `data/naruto_batch_005_claude_assignment.md` | Self-contained assignment and exact JSON contract |
| `docs/NARUTO_BATCH_005_RESEARCH_REPORT.md` | This report |
| `scripts/prepare_batch_005.py` | Reproducible catalogue/research generation |
| `scripts/finalize_batch_005.py` | Reproducible per-image manifest/status finalisation |

## 2. Selection method

The candidate pool came from the existing Dattebayo-derived `naruto_candidates.json`. Selection:

1. Excluded all identities in the original catalogue and Batches 003, 004-A and 004-B, using exact names plus normalised aliases (macrons, spelling variants and documented alias pairs).
2. Removed generic/rank-only entries, major Boruto-era protagonists, obvious filler categories and non-character entries.
3. Kept candidates with usable metadata: rank, affiliation, clan, title, classification or debut. This yielded 284 metadata-rich candidates.
4. Ranked by documented metadata richness and selected the top 100, with attention to specialist coverage (sensor, medical, Anbu, clan, swordsman, team/command roles).

This is an evidence-limited expansion, not a claim that every selected character has deep combat documentation. Many are minor canon characters. The assignment explicitly tells Claude not to invent feats and to prefer low-confidence/Held outcomes where evidence is thin.

### Identity checks

- Exact source-page names were preferred over normalised matching. This caught a collision where `Kosuke` (Kirigakure Anbu, `dattebayo:695`) could be wrongly matched to `Kōsuke` (messenger toad, `dattebayo:697`). The correct Kiri-nin is selected; the toad is not.
- `Nishi (sensor)` is a Boruto-era Konoha sensor/Jōnin and is retained for specialist coverage rather than treated as generic filler.
- `Third Mizukage`, `Mizunoto`, `Shin` and similar terse names refer to distinct source character pages, not generic rank labels.
- No duplicate identities were included in the final 100.

## 3. Research quality and evidence

Each research record contains factual metadata only: identity, aliases, debut, rank, classification, affiliation, clan, titles, status, team/occupation and evidence leads. No individual feat was invented or inferred as fact.

| Evidence level | Count | Meaning |
|---|---:|---|
| `inspected_secondary` | 2 | Fandom character page directly inspected during Stage 01; primary citations on that page were not opened. |
| `search_result_summary` | 98 | Dattebayo-derived metadata from the existing catalogue; source page not directly inspected in Stage 01. |

Directly inspected secondary pages:

- **Kosuke** (`dattebayo:695`): Kirigakure Anbu; page cites Fourth Databook p.207 and *Naruto* chapters 604–605 / *Shippūden* episode 345. The page states he was killed during Obito’s rampage and implies kenjutsu from his sword.
- **Nishi (sensor)** (`dattebayo:901`): Konoha sensor/Jōnin; page cites *Boruto* chapter 39 and anime episode 205 credits, and describes monitoring Kawaki and Boruto.

No primary manga chapter, databook page or anime episode was directly inspected in Stage 01. All chapter/databook references are leads, not verified primary quotations. Wiki/Fandom material is Tier 4 under the framework and cannot by itself establish a rating.

## 4. Artwork preparation

The existing image pipeline validated and downloaded artwork:

- **104 images total**: 103 from the original source URLs plus one corrected URL.
- **104 valid**, 0 invalid, 0 missing, 0 duplicates.
- **100/100 candidates have at least one valid image**; four candidates have two valid images.

Two source issues were found and resolved:

1. `Nishi (sensor)` source URL `.../f/f5/Nishi.png` returned HTTP 404. The manifest now uses `.../b/b2/Nishi_Infobox.png`, taken from the directly inspected character page.
2. `Kosuke` was initially mis-mapped to `Kōsuke` because normalised names collapsed. Correcting exact-name matching restored the valid `.../d/d0/Kosuke.png` image.

The per-image manifest records URL, source, status, dimensions, format, bytes, SHA-256 hash, local validated path, source accessibility, identity-review status, usage permissions and any error. **No publication permission was granted or claimed**; all rights remain “source-dependent; review before publication”. Artwork binaries are gitignored and were not committed.

## 5. Calibration

`naruto_batch_005_calibration.json` was derived from five local evaluation datasets. It separates:

- **reviewed_reference**: 20 Draft anchors, tiered R1 (6), R2 (7), R3 (7). They are local review references, not Approved records.
- **fit_reference**: the same anchors with Power values withheld, for the Fit-first pass.
- **power_reference**: the same anchors with Power values, opened only after Fit is fixed.
- **preliminary/disputed**: 93 non-anchor bulk drafts and an 18-name disputed watchlist. These are not anchors.
- **held_excluded**: 49 unique names held in any inspected snapshot, excluded from every rating example even where a later file promoted them to Draft.

Source counts are non-unique because the expansion file integrates 003/004 records. Nothing in the calibration is labelled approved, production-ready or publication-ready.

## 6. Unresolved cases and handoff constraints

- **Claude evaluation has not been supplied.** Integration into any production or evaluated dataset is intentionally not started.
- **Evidence depth is uneven.** Most records have only metadata-level evidence. High Fit/Power values must not be produced from rank, clan, affiliation or popularity alone.
- **Primary verification remains outstanding.** Claude should independently verify any feat used above the lower evidence bands, especially for disputed ECVs, conditional abilities and high ratings.
- **Enma is not a permanent exclusion.** Enma appears in prior Batch 004-B review/evaluation files but has no exact Dattebayo catalogue record and was unmatched during expansion integration. The research file and calibration both flag Enma as `manual_identity_mapping_required`. Resolve the identity manually before any future addition; do not fold Enma into Batch 005 by assumption.
- **No approval path has been executed.** All future Claude output must remain Draft/review until the owner explicitly approves it.

## 7. Reproduction

```powershell
python -m scripts.prepare_batch_005
python -m scripts.validate_naruto_images --catalogue data/naruto_batch_005_catalogue.json --output-dir data/naruto_images --report data/naruto_batch_005_image_manifest.json --concurrency 8
python -m scripts.finalize_batch_005
python -m pytest tests -q
```

`finalize_batch_005.py` must be run after image validation: it converts the validation summary into the per-image manifest and refreshes `image_status` in the research package.

## 8. Commit traceability

Stage 01 package commit on `content/naruto-batch-005`: `PENDING_PACKAGE_COMMIT`.

The report hash line is populated after the package commit so that the recorded value refers to a real pushed commit rather than a self-referential hash.
