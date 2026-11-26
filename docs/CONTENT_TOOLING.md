# Character Catalogue & Image Tooling

## Sources

- **Dattebayo API** (`https://dattebayo-api.onrender.com/characters`): used as the pilot Naruto/Shippuden/Boruto character source. It exposes 1,431 records with names, images, debut, classification, species, titles, and metadata. Availability depends on the free Render host; collection is retry-based.
- **Narutopedia profile URLs** are constructed but not verified as exact pages.
- Image URLs point to `static.wikia.nocookie.net`. They are validated technically but not semantically.

## Provider architecture

- `app/content/providers/base.py`: `CharacterProvider` contract and registry.
- `app/content/providers/dattebayo.py`: Dattebayo implementation with pagination, normalization, universe separation (Naruto vs Boruto), eligibility flags, and duplicate detection.
- Additional universes can be added by implementing `CharacterProvider` without changing the catalogue builder.

## Outputs

- `data/naruto_candidates.json`: machine-readable candidate catalogue.
- `data/naruto_candidates_ka_import.json`: KA-IMPORT-1.0 catalogue batch.
- `data/naruto_image_report.json`: image validation summary.
- `data/naruto_images/`: downloaded, validated image files.

## Eligibility and review

- Candidates with non-human species, filler/anime-only debuts, or missing manga debut are marked `canonical_eligibility = "uncertain"`.
- Boruto-era characters are separated via `universe = "Boruto"` and notes.
- All candidates remain `review_status = "pending"`; none are approved.
- No Power, Role Fit, or final rarity values are assigned.

## Image validation

- HTTP status and content-type handling.
- Magic-byte format detection (PNG, JPEG, GIF, WebP, BMP).
- Dimension parsing.
- Corruption markers (PNG IEND, JPEG EOI).
- Minimum dimension checks.
- Exact duplicate detection via SHA-256.
- No claim is made that an image depicts the correct character.