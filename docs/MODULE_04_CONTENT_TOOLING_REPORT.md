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

## Human review required

- 910 uncertain eligibility entries.
- 86 candidates without image URLs.
- 75 missing/failed image downloads.
- 1 invalid image.
- All Boruto-era candidates for separation decision.