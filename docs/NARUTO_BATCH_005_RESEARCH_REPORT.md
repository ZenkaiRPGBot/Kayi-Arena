# Naruto Batch 005 — corrective research quality report

**Date:** 2026-11-27  
**Branch:** `content/naruto-batch-005`  
**Frameworks:** `EVAL-FRAMEWORK-1.0` · `NARUTO-CANON-0.1` · `SCORE-1.0` (boundary reference) · `RARITY-0.2` (out of scope)  
**Status:** Corrective Stage 01B complete. No Power, Role Fit, rarity, score, approval or publication status has been allocated.

## 1. Diagnosis of the original deficiency

The first Batch 005 package was structurally complete but substantively incomplete.

- `naruto_batch_005_research.json` contained 100 records whose fields were generated from Dattebayo catalogue metadata: rank, affiliation, clan, titles, debut, classification and image status.
- Capability fields used boilerplate such as “No individual jutsu or combat feats are transcribed here”, “Claude must verify…”, “Rank: …”, “Affiliation: …” and “not recorded”. Those strings satisfy a JSON field check but are not research.
- Claude’s preserved evaluation correctly returned **1 Draft and 99 Held** records, with Power `1` for all 100 as a schema floor, Fit `0` for nearly all roles, and no A-grade evidence.
- The review notes explicitly identified the cause: no combat feats, durability feats or demonstrated abilities were supplied; rank, clan and affiliation were the only differentiators.

The defect was in the preparation pipeline, not in Claude’s evaluation. The old scripts treated “all fields present” as completion and did not distinguish catalogue, artwork, research, evaluation and publication readiness.

The original evaluation files are preserved unchanged for reference:

- `data/naruto_batch_005_original_claude_evaluation.json`
- `data/naruto_batch_005_original_evaluation_details.json`
- `data/naruto_batch_005_original_review_notes.md`

Their placeholder ratings have **not** been imported into any playable catalogue. The copies are byte-identical to the supplied Downloads files.

## 2. Corrective research method

1. Reused the existing stable character IDs, catalogue mappings and validated artwork from Stage 01. No artwork or catalogue identity work was repeated unnecessarily.
2. Fetched 284 eligible Naruto Fandom character pages through the MediaWiki API and produced cleaned, sectioned digests plus raw wikitext. Canonical chapter/episode/databook strings were retained from the raw page text.
3. Researched 156 candidates: the original 100 plus 56 non-duplicate Naruto-era replacement candidates from the same eligible pool.
4. Applied a strict gate:
   - **RESEARCH_READY** — at least one actually demonstrated technique, combat action, mission function or concrete specialist capability, plus a traceable inspected-secondary source.
   - **PARTIAL_RESEARCH** — specific detail exists but important demonstrated-use information is missing or vague.
   - **INSUFFICIENT_EVIDENCE** — only metadata, reputation, appearance, personality or generic statements.
5. Excluded adaptation-only evidence by default under `NARUTO-CANON-0.1` unless the same capability had a verified manga chapter or databook reference.
6. Checked every retained canonical reference against the inspected page text. Formatting differences such as doubled apostrophes and “pages” versus “page” were normalised, but a bare number elsewhere in the article was not accepted as proof. In final records, 16 unsupported reference strings were dropped.
7. Rebuilt the catalogue and research package from only research-ready candidates, then revalidated artwork for the final set.

No primary manga chapter, databook page or anime episode was directly opened in this stage. Fandom pages are treated as inspected secondary sources; chapter/databook references on those pages are leads, not primary quotations.

## 3. Actual research coverage

| Metric | Actual result |
|---|---:|
| Candidates researched | 156 |
| Original candidates researched | 100 |
| Replacement candidates researched | 56 |
| Initially RESEARCH_READY | 87 |
| PARTIAL_RESEARCH | 31 |
| INSUFFICIENT_EVIDENCE | 38 |
| Final research-ready candidates | **62** |
| Original candidates retained | 35 |
| Replacement candidates selected | 27 |
| Original candidates removed | 65 |
| Unresolved candidates preserved | 94 |
| Target of 100 reached | No — no padding used |

The final research package contains **150 demonstrated ability records** across 62 candidates. **39 of 62** records carry canonical chapter/episode/databook references checked against the inspected page text; all 62 carry a traceable source URL. The remaining 23 have only the inspected character page as a source locator.

Capability coverage includes 35 offensive, 24 defensive/durability, 18 speed/mobility, 27 leadership, 57 tactical, 17 stealth/infiltration, 52 support/control and 7 medical/healing summaries. Coverage is uneven and does not imply that every character has every capability.

## 4. Candidate quality and exclusions

### Excluded from the final package

- **38** insufficient-evidence original/replacement candidates: metadata, reputation or generic prose only.
- **31** partial-research candidates: one duty or vague capability without sufficient demonstrated use.
- **23** adaptation-only research-ready candidates: demonstrated ability existed, but only in anime/game/movie material with no verified manga chapter or databook reference. Examples include Yoshino Nara and Ensui Nara.
- **1** continuity exclusion: **Shin Uchiha** (`dattebayo:1309`) is a Boruto-era arc antagonist whose clone group creates an identity and ECV ambiguity. It is preserved as unresolved, not permanently deleted.
- **1** artwork exclusion: **Musai** (`dattebayo:855`) had a source image URL returning HTTP 404 and no single-character infobox image on the inspected page; a two-character group image was not substituted.

Some research-ready candidates were not selected because better-documented replacements scored higher; they remain in the unresolved file without placeholder ratings. All 94 unresolved cases are in `data/naruto_batch_005_unresolved_candidates.json` with their gate status, origin and reason.

### Identity and continuity decisions

- `Kosuke` (`dattebayo:695`) is the Kirigakure Anbu. The inspected page only says Anbu status is “presumably” skilled and that a sword implies kenjutsu; he is unresolved rather than rated from implication.
- `Kōsuke` the messenger toad was never selected. Macron/spelling similarity is not an identity merge.
- `Shin` (`dattebayo:1094`) is Sai’s Root brother and is distinct from Shin Uchiha. He remains research-ready based on demonstrated kenjutsu, taijutsu against Anbu clones and reincarnation-war actions.
- `Nishi (sensor)` (`dattebayo:901`) remains as a Boruto-era sensor/Jōnin with an explicit ECV and no verified chapter citation; she is traceable but is not treated as a Naruto-era combat anchor.
- `Enma` remains `manual_identity_mapping_required`; it is not a permanent exclusion and is not one of the 62.

## 5. Artwork

After the final research gate, the revised catalogue was revalidated:

- **63 images total**, 63 valid, 0 invalid, 0 missing, 0 duplicates.
- **62/62 candidates** have at least one validated image; one candidate has two.
- Per-image manifest records URL, source, status, dimensions, format, bytes, SHA-256 hash, local path, accessibility, identity-review status and usage permissions.
- Rights remain **source-dependent; review before publication**. No publication permission was granted or claimed.

Artwork confirms the selected source record only; it is not ability evidence.

## 6. Pipeline improvement

New and updated scripts now keep the five completion concepts separate:

- `scripts/batch_005_quality.py` — substantive-field detection, research-ready validation, staged completion report builder.
- `scripts/validate_batch_005_quality.py` — writes `data/naruto_batch_005_completeness_report.json`.
- `scripts/build_batch_005_corrected.py` — rebuilds the package from gated research only.
- `scripts/write_batch_005_artwork_exclusions.py` — records artwork failures for the build.
- `scripts/prepare_batch_005.py` — now marks its output `INSUFFICIENT_EVIDENCE` and reports `research_ready=0`; it can no longer be mistaken for a Claude-ready package.
- `tests/test_batch_005_research_quality.py` — focused gate tests.

The completeness report currently records:

- catalogue: complete
- artwork: complete
- research gate: complete, with 62 research-ready records
- evaluation: not complete
- publication: not ready

Fields containing only “not recorded”, “unknown”, rank/affiliation/clan/debut boilerplate, “Claude should…” or similar placeholders no longer count as substantive research.

## 7. Deliverables

- `data/naruto_batch_005_research.json` — 62 research-ready candidates, no ratings.
- `data/naruto_batch_005_catalogue.json` — updated 62-candidate catalogue.
- `data/naruto_batch_005_unresolved_candidates.json` — 94 unresolved/excluded cases.
- `data/naruto_batch_005_selection_summary.json` — actual counts and exclusions.
- `data/naruto_batch_005_completeness_report.json` — five-stage completion status.
- `data/naruto_batch_005_claude_assignment.md` — revised self-contained assignment.
- `data/naruto_batch_005_change_log.json` — concise change log.
- `docs/NARUTO_BATCH_005_RESEARCH_REPORT.md` — this report.
- Preserved original evaluation files listed in section 1.

## 8. Remaining limitations

- Evidence is secondary-source based; no primary chapter/databook/anime verification was performed.
- 23 of 62 records have no canonical ref beyond the source page URL.
- 11 of 62 records describe an anime-only or adaptation-sensitive ECV; Claude must state the ECV and avoid cross-version composites.
- Low-evidence minors remain low-confidence even after passing the gate.
- Claude must perform the first real evaluation. No placeholder Power 1 or Fit 0 from the preserved evaluation is a rating decision.

## 9. Verification

- Focused quality tests: **7 passed**.
- Full suite result: **167 passed**.
- Stage 01B package commit: `PENDING_PACKAGE_COMMIT`.

The test line and commit are populated after verification so the report refers to real results and a real commit.
