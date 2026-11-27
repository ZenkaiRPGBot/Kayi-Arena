# Naruto Batch 003 — Content Preparation Report

## Summary

- Target characters: **50**
- Matched to catalogue: **49**
- Unmatched: **1** (`C (Hidden Cloud shinobi)` — no Dattebayo record found)
- Image URLs available: **49/49** (all matched candidates have at least one image)
- Technically valid images: pending validation on full catalogue run

## Unmatched

- `C (Hidden Cloud shinobi)`: no candidate found in the Dattebayo catalogue. Manual resolution or alternate source required.

## Deliverables

- `data/naruto_batch_003_catalogue.json`
- `data/naruto_batch_003_image_manifest.json`
- `data/naruto_batch_003_ka_import.json` (KA-IMPORT-1.0, draft)
- `data/naruto_batch_003_review_gallery.html`

## Integration results

- Records integrated: **49** (1 unmatched: `C (Kumogakure shinobi)`)
- Held: **1** (Roshi)
- Draft: **48**
- Rarity distribution: Uncommon 32, Common 12, Rare 4, Epic 1
- Balance simulation: 5,000 drafts, 0 failures, avg 28 actions, first-player win rate 48.94%

## Targeted research corrections applied

- Dan Kato: Held → Draft (Ghost Transformation Jutsu, Ch. 591)
- Mabui: Held → Draft; Support 2→3 (Heavenly Transfer, Ch. 562)
- Yugito Nii: evidence corrected (captured by Hidan and Kakuzu, not Deidara)
- Choji Akimichi: canonical version updated (Butterfly Mode without pills, Ch. 533)
- Shizune: Captain 2→3, Healer 3→4 (Medical Division captain)
- Jugo: Healer 0→2 (Cellular Regeneration Ejection, Ch. 414)
- Karin: Healer 3 (no change, Heal Bite confirmed)
- Ino/Inoichi: Support maintained at 4 each

## Deliverables

- `data/naruto_batch_003_evaluated_dataset.json`
- `data/naruto_batch_003_integration_report.json`
- `data/naruto_batch_003_review_gallery_evaluated.html`
- `data/naruto_batch_003_balance_report.json`
- `data/naruto_batch_003_change_log.json`