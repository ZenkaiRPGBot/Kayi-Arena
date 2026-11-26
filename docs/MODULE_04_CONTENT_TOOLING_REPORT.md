# Module 4 Content Tooling Implementation Report

## Summary

Reusable character catalogue collection and image validation tooling has been implemented on branch `feature/character-content-tools`. Naruto and Naruto Shippuden are the pilot universe. The production character database was not modified.

## Character collection

- Source: Dattebayo API (`https://dattebayo-api.onrender.com/characters`)
- Unique candidates discovered: **1,429**
- Duplicate entries identified and removed: **2**
- Naruto/Shippuden-era candidates: **1,159**
- Boruto-era candidates separated for review: **270**
- Candidates with at least one image URL: **1,343**
- Candidates with no image URL: **86**
- Total image URLs collected: **1,410**
- Uncertain eligibility entries: **910**

## Image validation

- Total image URLs processed: **1,410**
- Successfully downloaded and technically valid: **1,333**
- Invalid (bad format/dimensions/corruption): **1**
- Missing/failed downloads: **75**
- Exact duplicate images detected: **1**

## Eligibility handling

- Non-human or special species are marked `canonical_eligibility = "uncertain"`.
- Filler/anime-only or manga-less debuts are marked uncertain.
- Boruto-era characters are separated via `universe = "Boruto"` and notes.
- All candidates remain `review_status = "pending"`; none are approved.
- No Power, Role Fit, or final rarity values were assigned. `rarity` is exported as a provisional `Common` placeholder per KA-IMPORT-1.0, which Claude may replace during evaluation.

## Outputs

- `data/naruto_candidates.json`
- `data/naruto_candidates_ka_import.json` (KA-IMPORT-1.0, `batch_type = "catalogue"`)
- `data/naruto_image_report.json`
- `data/naruto_images/` (1,333 validated image files)

## Source limitations

- Dattebayo API is hosted on Render Free and may be slow or unavailable; collection is retry-based.
- Narutopedia profile URLs are constructed, not verified.
- Wikia image hotlinks may change or be restricted; downloads record failures rather than bypassing restrictions.
- Automated validation does not verify that an image depicts the correct character.

## Testing

- Deterministic unit tests cover catalogue deduplication, image format/dimension/corruption/duplicate detection, provider mapping, and KA-IMPORT-1.0 export.
- Network-dependent collection is kept separate from deterministic tests.
- Full test suite result: **84 passed, 0 failures**.

## Reconciliation results (Module 4C)

- Priority roster size: **60**
- Matched to catalogue: **60/60**
- Unmatched: **0** (Ashura Otsutsuki resolved to "Asura Ōtsutsuki")
- Image manifest entries: **60**
- Curated Naruto roster groups: ready_for_evaluation=59, insufficient_canonical_evidence=3, canon_or_eligibility_disputed=324, duplicate_or_alternate_version=3, filler_exclusive=375, image_requires_review=395

## Evidence verification leads (proposed, not verified)

- Naruto retained Six Paths powers: verify against manga chapters 695-699 and 700; wiki lead only.
- Sasuke retained Rinnegan/Susanoo: verify against chapters 699-700.
- Madara/Obito jinchuriki sustainability: verify against chapters 658-678 and 600-610.
- Naruto healing others: verify against medical ninjutsu feats; wiki lead only.
- Kakashi borrowed Obito powers: verify against chapters 680-690.
- Rock Lee Gates: verify against chapters 66-72 and 671-672.
- Sakura advanced healing: verify against chapters 254-265 and 539-540.
- Tsunade/Katsuyu contributions: verify against chapters 148-171 and 632.
- Kurama independent abilities: verify against chapters 567-570.
- Edo Tensei characters: verify living feats vs reanimation-only feats.

## Human review required

- 910 uncertain eligibility entries.
- 86 candidates without image URLs.
- 75 missing/failed image downloads.
- 1 invalid image.
- All Boruto-era candidates for separation decision.
- 7 Held records from evaluation batches are preserved as Held, not approved.